import os
import json
from typing import Dict, Any, List, Optional, TypedDict, Literal
import google.generativeai as genai
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END

# Load environment variables
load_dotenv()

# ==========================================
# 1. LANGGRAPH STATE DEFINITION
# ==========================================
class AgentState(TypedDict):
    """The central state dictionary carried through the LangGraph StateGraph."""
    stage: Literal["FAQ", "QUALIFICATION", "ESCALATED", "COMPLETED"]
    messages: List[Dict[str, str]]
    lead_info: Dict[str, Optional[str]]
    out_of_scope_count: int
    escalated: bool
    escalation_reason: Optional[str]
    summary: Optional[Dict[str, Any]]
    latest_user_message: str
    assistant_reply: str


# ==========================================
# 2. CORE WORKFLOW CLASS & GRAPH NODES
# ==========================================
class ClosiraWorkflow:
    """Manages the LangGraph instance and provides node/edge implementations using Google Gemini."""
    def __init__(self, sop_path: str = "sop.json"):
        # Initialize Google Generative AI Client
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY not found in environment. Please set it in a .env file."
            )
        genai.configure(api_key=api_key)
        self.model = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
        
        # Load SOP Data
        if not os.path.exists(sop_path):
            raise FileNotFoundError(f"SOP configuration file not found at: {sop_path}")
        with open(sop_path, "r", encoding="utf-8") as f:
            self.sop_data = json.load(f)

        # Build and Compile the LangGraph
        self.graph = self._build_graph()

    def _get_system_prompt(self, state: AgentState) -> str:
        """Generates the system prompt based on current graph state."""
        sop_str = json.dumps(self.sop_data, indent=2)
        lead_info_str = json.dumps(state["lead_info"], indent=2)
        
        return f"""You are "Bloom Bot", an AI receptionist for Bloom Aesthetics Clinic, a premium medical aesthetics clinic.
Your communication style is warm, professional, extremely helpful, yet firm on clinic boundaries.

You operate strictly under the following Standard Operating Procedure (SOP):
{sop_str}

=== CRITICAL RELIABILITY & SAFETY RULES ===
1. FAQ ANSWERING GROUNDING: You MUST only answer customer inquiries using the information directly stated in the SOP.
   - DO NOT make up prices, services, hours, or policies not in the SOP.
   - If a customer asks about a service or policy not listed (e.g. laser hair removal, microneedling, refunds), you MUST acknowledge that we do not have that information or offer that service, treat it as out-of-scope, and transition to escalation if required.
   
2. STRICT ESCALATION TRIGGERS: You must immediately request human handoff (stage "ESCALATED") if:
   - The user complains, expresses frustration, or talks about a bad experience.
   - The user asks a MEDICAL question (e.g., "Will Botox hurt?", "Are there side effects?", "Is Botox safe during pregnancy?").
   - The user tries to NEGOTIATE pricing or asks for custom discounts (e.g., "Can I get £20 off?", "Is the price negotiable?").
   - The user explicitly asks for a human, receptionist, or manager.
   - The user asks a question completely out-of-scope of the SOP.

3. LEAD QUALIFICATION STAGE:
   - When the user expresses interest in booking an appointment, or once their initial FAQ is answered, transition to the "QUALIFICATION" stage.
   - In "QUALIFICATION" stage, you must ask the customer the following 3 structured questions one by one (never ask all three in a single turn):
     1. Which service are you looking to book (Botox, Fillers, or a general Consultation)?
     2. Have you had treatments with us before (New client or Existing client)?
     3. What is your preferred day or time range for an appointment (we are open Mon-Sat, 9 am - 7 pm)?
   - Fill in the 'extracted_lead_info' fields as the user answers them.
   - Once all three fields are completed, transition to "COMPLETED".

=== CURRENT CONVERSATION STATE ===
- Current Stage: {state["stage"]}
- Collected Lead Info: {lead_info_str}
- Number of Out-of-Scope Questions so far: {state["out_of_scope_count"]}

=== RESPONSE FORMAT ===
You MUST respond with a single valid JSON object containing the exact keys listed below:
{{
  "assistant_reply": "Friendly response to the user",
  "stage": "FAQ" | "QUALIFICATION" | "ESCALATED" | "COMPLETED",
  "is_out_of_scope": true | false,
  "is_unanswered": true | false,
  "escalation_triggered": true | false,
  "escalation_reason": "Reason string" | null,
  "extracted_lead_info": {{
    "service_interested": "Botox" | "Fillers" | "Consultation" | null,
    "client_status": "New" | "Existing" | null,
    "preferred_time": "Preferred time slot string" | null
  }}
}}
"""

    def _format_gemini_messages(self, state: AgentState) -> List[Dict[str, Any]]:
        """Formats the alternating user/model message history for the Gemini API."""
        contents = []
        for msg in state["messages"][-14:]:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({"role": role, "parts": [msg["content"]]})
        contents.append({"role": "user", "parts": [state["latest_user_message"]]})
        return contents

    # ==========================================
    # GRAPH NODES DEFINITIONS
    # ==========================================
    def faq_node(self, state: AgentState) -> Dict[str, Any]:
        """FAQ Node: Evaluates and answers customer general questions using Gemini."""
        system_prompt = self._get_system_prompt(state)
        gemini_contents = self._format_gemini_messages(state)

        try:
            # Configure Gemini Generative Model with native system prompt and JSON mime type
            model = genai.GenerativeModel(
                model_name=self.model,
                system_instruction=system_prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            response = model.generate_content(gemini_contents)
            response_text = response.text.strip()
            
            result_json = json.loads(response_text)
        except Exception as e:
            return self._trigger_fallback(state, f"FAQ processing API failure: {str(e)}")

        # Calculate values
        out_of_scope_inc = 1 if (result_json.get("is_out_of_scope", False) or result_json.get("is_unanswered", False)) else 0
        new_out_of_scope_count = state["out_of_scope_count"] + out_of_scope_inc
        
        # Build state updates
        lead_info = state["lead_info"].copy()
        extracted = result_json.get("extracted_lead_info", {})
        for k in ["service_interested", "client_status", "preferred_time"]:
            if extracted.get(k) is not None:
                lead_info[k] = extracted.get(k)

        escalation_triggered = result_json.get("escalation_triggered", False)
        escalation_reason = result_json.get("escalation_reason")
        
        # Handle programmatic out-of-scope overrides
        if new_out_of_scope_count > 2 and not escalation_triggered:
            escalation_triggered = True
            escalation_reason = "More than 2 unanswered or out-of-scope questions asked."
            reply = "I apologize, but I want to make sure you get the most accurate assistance. I am transferring you to one of our clinic coordinators who will help you further."
        else:
            reply = result_json.get("assistant_reply", "")

        new_messages = state["messages"].copy()
        new_messages.append({"role": "user", "content": state["latest_user_message"]})
        new_messages.append({"role": "assistant", "content": reply})

        return {
            "stage": "ESCALATED" if escalation_triggered else result_json.get("stage", "FAQ"),
            "messages": new_messages,
            "lead_info": lead_info,
            "out_of_scope_count": new_out_of_scope_count,
            "escalated": escalation_triggered,
            "escalation_reason": escalation_reason,
            "assistant_reply": reply
        }

    def qualification_node(self, state: AgentState) -> Dict[str, Any]:
        """Qualification Node: Asks structured questions using Gemini to complete the booking."""
        system_prompt = self._get_system_prompt(state)
        gemini_contents = self._format_gemini_messages(state)

        try:
            model = genai.GenerativeModel(
                model_name=self.model,
                system_instruction=system_prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            response = model.generate_content(gemini_contents)
            response_text = response.text.strip()
            
            result_json = json.loads(response_text)
        except Exception as e:
            return self._trigger_fallback(state, f"Qualification processing API failure: {str(e)}")

        out_of_scope_inc = 1 if (result_json.get("is_out_of_scope", False) or result_json.get("is_unanswered", False)) else 0
        new_out_of_scope_count = state["out_of_scope_count"] + out_of_scope_inc
        
        lead_info = state["lead_info"].copy()
        extracted = result_json.get("extracted_lead_info", {})
        for k in ["service_interested", "client_status", "preferred_time"]:
            if extracted.get(k) is not None:
                lead_info[k] = extracted.get(k)

        escalation_triggered = result_json.get("escalation_triggered", False)
        escalation_reason = result_json.get("escalation_reason")

        if new_out_of_scope_count > 2 and not escalation_triggered:
            escalation_triggered = True
            escalation_reason = "More than 2 unanswered or out-of-scope questions asked."
            reply = "I apologize, but I want to make sure you get the most accurate assistance. I am transferring you to one of our clinic coordinators who will help you further."
        else:
            reply = result_json.get("assistant_reply", "")

        new_messages = state["messages"].copy()
        new_messages.append({"role": "user", "content": state["latest_user_message"]})
        new_messages.append({"role": "assistant", "content": reply})

        # Check if all lead values are captured to auto-complete
        final_stage = result_json.get("stage", "QUALIFICATION")
        if all(lead_info.values()) and not escalation_triggered:
            final_stage = "COMPLETED"

        return {
            "stage": "ESCALATED" if escalation_triggered else final_stage,
            "messages": new_messages,
            "lead_info": lead_info,
            "out_of_scope_count": new_out_of_scope_count,
            "escalated": escalation_triggered,
            "escalation_reason": escalation_reason,
            "assistant_reply": reply
        }

    def escalate_node(self, state: AgentState) -> Dict[str, Any]:
        """Escalate Node: Politely hands off to a human and closes transaction."""
        reply = "Our customer care team has been notified and will be in touch with you shortly. Thank you for your patience!"
        
        if state["assistant_reply"] and state["stage"] == "ESCALATED":
            reply = state["assistant_reply"]

        new_messages = state["messages"].copy()
        if not new_messages or new_messages[-1]["content"] != reply:
            new_messages.append({"role": "assistant", "content": reply})

        return {
            "stage": "ESCALATED",
            "messages": new_messages,
            "escalated": True,
            "assistant_reply": reply
        }

    def summarize_node(self, state: AgentState) -> Dict[str, Any]:
        """Summarize Node: Generates session audit summaries using Gemini."""
        history_str = ""
        for msg in state["messages"]:
            history_str += f"{msg['role'].upper()}: {msg['content']}\n"

        summary_prompt = f"""You are the audit logger for Bloom Aesthetics Clinic.
Your job is to read the following conversation log and output a highly structured, accurate JSON summary of the session.

=== CONVERSATION LOG ===
{history_str}

=== CURRENT SESSION META ===
- Final Stage: {state["stage"]}
- Lead Info Collected: {json.dumps(state["lead_info"])}
- Escalation Reason: {state["escalation_reason"]}

=== OUTPUT FORMAT ===
You must respond with a valid JSON object ONLY containing the exact keys:
- "customer_intent": A concise description of what the customer wanted.
- "key_details_collected": A JSON object showing the collected lead details (service_interested, client_status, preferred_time).
- "sop_gaps_identified": A list of questions or topics the customer asked that were not covered in the clinic's SOP, or an empty list if none.
- "recommended_next_action": What the clinic staff or system should do next.
"""
        try:
            model = genai.GenerativeModel(
                model_name=self.model,
                system_instruction=summary_prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            response = model.generate_content("Please output the structured JSON log now.")
            response_text = response.text.strip()
            
            summary = json.loads(response_text)
        except Exception as e:
            summary = {
                "customer_intent": "Unknown due to summary processing failure",
                "key_details_collected": state["lead_info"],
                "sop_gaps_identified": [f"Summary Error: {str(e)}"],
                "recommended_next_action": "Coordinator to manually inspect logs."
            }

        return {
            "summary": summary
        }

    # ==========================================
    # GRAPH EDGES & ROUTING
    # ==========================================
    def _route_stage(self, state: AgentState) -> Literal["FAQ", "QUALIFICATION", "escalate_node", "summarize_node"]:
        """Conditional routing helper based on state parameters."""
        if state["stage"] == "ESCALATED" or state["escalated"]:
            return "escalate_node"
        if state["stage"] == "COMPLETED":
            return "summarize_node"
        if state["stage"] == "QUALIFICATION":
            return "QUALIFICATION"
        return "FAQ"

    def _should_end(self, state: AgentState) -> Literal["summarize_node", "__end__"]:
        """Decides if the escalated conversation needs an final summarization step."""
        if state["stage"] == "ESCALATED" and not state["summary"]:
            return "summarize_node"
        return "__end__"

    def _trigger_fallback(self, state: AgentState, error_reason: str) -> Dict[str, Any]:
        """Prepares state updates to fallback and escalate on system failures."""
        reply = "I'm having a brief connection issue. Let me get a human agent to assist you immediately."
        new_messages = state["messages"].copy()
        new_messages.append({"role": "user", "content": state["latest_user_message"]})
        new_messages.append({"role": "assistant", "content": reply})

        return {
            "stage": "ESCALATED",
            "messages": new_messages,
            "escalated": True,
            "escalation_reason": error_reason,
            "assistant_reply": reply
        }

    # ==========================================
    # GRAPH COMPILATION
    # ==========================================
    def _build_graph(self):
        """Builds and compiles the LangGraph StateGraph pipeline."""
        builder = StateGraph(AgentState)

        # Define Nodes
        builder.add_node("FAQ", self.faq_node)
        builder.add_node("QUALIFICATION", self.qualification_node)
        builder.add_node("escalate_node", self.escalate_node)
        builder.add_node("summarize_node", self.summarize_node)

        # Establish Entry Point
        builder.set_entry_point("FAQ")

        # Configure Conditional Edges from FAQ
        builder.add_conditional_edges(
            "FAQ",
            self._route_stage,
            {
                "FAQ": "FAQ",
                "QUALIFICATION": "QUALIFICATION",
                "escalate_node": "escalate_node",
                "summarize_node": "summarize_node"
            }
        )

        # Configure Conditional Edges from QUALIFICATION
        builder.add_conditional_edges(
            "QUALIFICATION",
            self._route_stage,
            {
                "FAQ": "FAQ",
                "QUALIFICATION": "QUALIFICATION",
                "escalate_node": "escalate_node",
                "summarize_node": "summarize_node"
            }
        )

        # Escalate node transition to summarize
        builder.add_conditional_edges(
            "escalate_node",
            self._should_end,
            {
                "summarize_node": "summarize_node",
                "__end__": END
            }
        )

        # Summary node concludes the graph
        builder.add_edge("summarize_node", END)

        return builder.compile()

    def process_message(self, state_dict: Dict[str, Any], user_message: str) -> Dict[str, Any]:
        """Main interface to run user inputs through the compiled StateGraph."""
        current_state = {
            "stage": state_dict.get("stage", "FAQ"),
            "messages": state_dict.get("messages", []),
            "lead_info": state_dict.get("lead_info", {"service_interested": None, "client_status": None, "preferred_time": None}),
            "out_of_scope_count": state_dict.get("out_of_scope_count", 0),
            "escalated": state_dict.get("escalated", False),
            "escalation_reason": state_dict.get("escalation_reason", None),
            "summary": state_dict.get("summary", None),
            "latest_user_message": user_message,
            "assistant_reply": ""
        }

        if current_state["stage"] == "ESCALATED" and current_state["summary"]:
            return current_state
        if current_state["stage"] == "COMPLETED" and current_state["summary"]:
            return current_state

        target_node = current_state["stage"]
        if target_node not in ["FAQ", "QUALIFICATION"]:
            target_node = "FAQ"

        final_state = self.graph.invoke(current_state, {"recursion_limit": 10})
        return final_state
