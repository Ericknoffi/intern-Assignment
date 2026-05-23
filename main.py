import os
import sys
import json
import argparse
from typing import List
from workflow import ClosiraWorkflow

# Ensure the transcripts directory exists
TRANSCRIPTS_DIR = "test_transcripts"

class SimpleSessionState:
    """A helper class to preserve conversation parameters matching our previous interface."""
    def __init__(self):
        self.stage = "FAQ"
        self.messages = []
        self.lead_info = {
            "service_interested": None,
            "client_status": None,
            "preferred_time": None
        }
        self.out_of_scope_count = 0
        self.escalated = False
        self.escalation_reason = None
        self.summary = None

    def to_dict(self):
        return {
            "stage": self.stage,
            "messages": self.messages,
            "lead_info": self.lead_info,
            "out_of_scope_count": self.out_of_scope_count,
            "escalated": self.escalated,
            "escalation_reason": self.escalation_reason,
            "summary": self.summary
        }

    def update_from_dict(self, d: dict):
        self.stage = d.get("stage", self.stage)
        self.messages = d.get("messages", self.messages)
        self.lead_info = d.get("lead_info", self.lead_info)
        self.out_of_scope_count = d.get("out_of_scope_count", self.out_of_scope_count)
        self.escalated = d.get("escalated", self.escalated)
        self.escalation_reason = d.get("escalation_reason", self.escalation_reason)
        self.summary = d.get("summary", self.summary)


def parse_args():
    parser = argparse.ArgumentParser(description="Closira AI Support Agent CLI and Simulator (LangGraph Edition)")
    parser.add_argument(
        "--interactive", "-i", action="store_true", help="Run the agent in interactive chat mode in the terminal."
    )
    parser.add_argument(
        "--run-simulations", "-s", action="store_true", help="Run the 5 pre-defined simulation scenarios and save transcripts."
    )
    return parser.parse_args()


def run_interactive():
    """Runs a live interactive chat session in the terminal."""
    print("=" * 60)
    print("      BLOOM AESTHETICS CLINIC - LANGGRAPH RECEPTIONIST      ")
    print("=" * 60)
    print("Initializing Closira LangGraph Workflow Engine...")
    
    try:
        workflow = ClosiraWorkflow()
        session = SimpleSessionState()
    except Exception as e:
        print(f"\n[ERROR] Initialization failed: {e}")
        print("Please ensure your .env file is set up and contains GEMINI_API_KEY.\n")
        return

    print("\nBloom Bot: Hello! Welcome to Bloom Aesthetics Clinic. How can I help you today?")
    print("(Type 'exit' or 'quit' to end the session)\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting. Goodbye!")
            break

        if not user_input:
            continue

        if user_input.lower() in ["exit", "quit"]:
            print("Ending session. Goodbye!")
            break

        print("Bloom Bot: ... thinking ...", end="\r")
        # Run state dictionary through the graph
        state_dict = session.to_dict()
        graph_output = workflow.process_message(state_dict, user_input)
        session.update_from_dict(graph_output)

        reply = graph_output.get("assistant_reply", "")
        # Clear thinking line
        print(" " * 30, end="\r")
        print(f"Bloom Bot: {reply}\n")

        # If session transitioned to completed or escalated, display the final audit summary
        if session.stage in ["ESCALATED", "COMPLETED"]:
            print("=" * 60)
            status_text = "⚠️ ESCALATED TO HUMAN" if session.stage == "ESCALATED" else "✅ SESSION COMPLETED"
            print(f"               {status_text}               ")
            print("=" * 60)
            if session.summary:
                print(json.dumps(session.summary, indent=2))
            print("=" * 60)
            break


def run_single_simulation(workflow: ClosiraWorkflow, scenario_name: str, file_name: str, inputs: List[str]):
    """Runs a sequence of user inputs through the workflow and saves the resulting markdown transcript."""
    print(f"\nRunning Scenario: {scenario_name}...")
    
    session = SimpleSessionState()
    transcript_md = f"# Test Transcript: {scenario_name}\n\n"
    transcript_md += "## Session Details\n"
    transcript_md += f"- **Target Scenario**: {scenario_name}\n"
    transcript_md += "- **Engine**: LangGraph StateGraph Pipeline\n\n"
    
    transcript_md += "## Conversation History\n\n"
    
    # Opening greeting simulation
    greeting = "Hello! Welcome to Bloom Aesthetics Clinic. How can I help you today?"
    transcript_md += f"**Bloom Bot**: {greeting}\n\n"
    print(f"  Bloom Bot: {greeting}")

    for user_input in inputs:
        transcript_md += f"**Customer**: {user_input}\n\n"
        print(f"  Customer: {user_input}")
        
        state_dict = session.to_dict()
        graph_output = workflow.process_message(state_dict, user_input)
        session.update_from_dict(graph_output)
        
        reply = graph_output.get("assistant_reply", "")
        
        transcript_md += f"**Bloom Bot**: {reply}\n\n"
        print(f"  Bloom Bot: {reply}")

        if session.stage in ["ESCALATED", "COMPLETED"]:
            break

    # Add final status and summary if generated
    transcript_md += "---\n\n## Session Outcome\n"
    transcript_md += f"- **Final Stage**: `{session.stage}`\n"
    if session.escalated:
        transcript_md += f"- **Escalation Reason**: {session.escalation_reason}\n"
    
    if session.summary:
        transcript_md += "\n### Generated Conversation Summary (JSON)\n"
        transcript_md += f"```json\n{json.dumps(session.summary, indent=2)}\n```\n"
        print(f"\n[Summary] {json.dumps(session.summary, indent=2)}")

    # Ensure transcripts folder exists
    os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)
    file_path = os.path.join(TRANSCRIPTS_DIR, file_name)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(transcript_md)
        
    print(f"Saved transcript to: {file_path}")
    print("-" * 60)


def run_all_simulations():
    """Runs the 5 pre-defined test scenarios required by the assignment."""
    print("=" * 60)
    print("         RUNNING AUTOMATED SCENARIO SIMULATIONS          ")
    print("=" * 60)

    try:
        workflow = ClosiraWorkflow()
    except Exception as e:
        print(f"[ERROR] Initialization failed: {e}")
        print("Please ensure your .env file contains a valid GEMINI_API_KEY.")
        sys.exit(1)

    # Scenario 1: In-SOP Question
    run_single_simulation(
        workflow,
        scenario_name="1. In-SOP Question",
        file_name="1_in_sop_question.md",
        inputs=[
            "What are your Botox prices?",
            "What are your opening hours?",
            "Thanks, that is all I needed!"
        ]
    )

    # Scenario 2: Out-of-Scope Question
    run_single_simulation(
        workflow,
        scenario_name="2. Out-of-Scope Question",
        file_name="2_out_of_scope.md",
        inputs=[
            "Hi, do you offer laser hair removal treatments?",
            "Ah, I see. What about microneedling?",
            "Oh, okay, do you have any services that do that?",
            "No worries then."
        ]
    )

    # Scenario 3: Escalation Trigger (Medical Inquiry / Pricing Negotiation)
    run_single_simulation(
        workflow,
        scenario_name="3. Escalation Trigger",
        file_name="3_escalation_trigger.md",
        inputs=[
            "Hi, I want to ask: is Botox safe to do while breastfeeding? Are there severe side effects?",
        ]
    )

    # Scenario 4: Lead Qualification
    run_single_simulation(
        workflow,
        scenario_name="4. Lead Qualification",
        file_name="4_lead_qualification.md",
        inputs=[
            "Hi! I would like to book an appointment with the clinic.",
            "I want to book a Botox treatment please.",
            "Yes, I am a new client.",
            "I would prefer next Saturday afternoon if possible."
        ]
    )

    # Scenario 5: Conversation Summary Verification
    # This runs a complete conversation and verifies the summary.
    # We will run a session that starts with an FAQ, proceeds to booking, completes, and showcases the summary output.
    run_single_simulation(
        workflow,
        scenario_name="5. Full Conversation & Summary",
        file_name="5_conversation_summary.md",
        inputs=[
            "Hi, what is your website address for bookings and what are your Botox rates?",
            "Great, I would love to schedule a Botox session.",
            "I am an existing client of the clinic.",
            "Do you have anything on Monday morning at 10 am?"
        ]
    )

    print("\nAll simulations completed successfully! Check the 'test_transcripts' folder.")


def main():
    args = parse_args()
    
    # If no flags are provided, show help
    if not (args.interactive or args.run_simulations):
        print("No operation mode specified.")
        print("Use --interactive (-i) to run in interactive CLI mode.")
        print("Use --run-simulations (-s) to run the test scenarios.")
        sys.exit(0)

    if args.interactive:
        run_interactive()
    elif args.run_simulations:
        run_all_simulations()


if __name__ == "__main__":
    main()
