# Test Transcript: 2. Out-of-Scope Question

## Session Details
- **Target Scenario**: 2. Out-of-Scope Question
- **Engine**: LangGraph StateGraph Pipeline
- **Focus**: Verifying that the FAQ node flags out-of-scope queries and that the graph programmatically transitions to the Escalation node once the threshold is exceeded (> 2 unanswered questions).

## Conversation History

**Bloom Bot**: Hello! Welcome to Bloom Aesthetics Clinic. How can I help you today?

**Customer**: Hi, do you offer laser hair removal treatments?

**Bloom Bot**: We do not currently offer laser hair removal treatments at Bloom Aesthetics Clinic. Our available services are Botox, Fillers, and free consultations. Would you like to hear about any of those?
*(Out of Scope Count: 1)*

**Customer**: Ah, I see. What about microneedling?

**Bloom Bot**: We also do not offer microneedling services. I apologize for any inconvenience. I can help you book a free consultation to discuss our other treatments if you would like?
*(Out of Scope Count: 2)*

**Customer**: Oh, okay, do you have any services that do that?

**Bloom Bot**: I apologize, but we only specialize in Botox, Fillers, and consultations as outlined in our guidelines. To ensure you get the absolute best care, let me transfer you to a clinic coordinator who can assist you further or recommend external services!
*(Out of Scope Count: 3 - Programmatic Escalation Router Triggered)*

---

## Session Outcome
- **Final Stage**: `ESCALATED`
- **Escalation Reason**: More than 2 unanswered or out-of-scope questions asked.

### Generated Conversation Summary (JSON)
```json
{
  "customer_intent": "Inquired about laser hair removal, microneedling, and other alternative procedures not offered by the clinic.",
  "key_details_collected": {
    "service_interested": null,
    "client_status": null,
    "preferred_time": null
  },
  "sop_gaps_identified": [
    "laser hair removal",
    "microneedling",
    "alternative skincare services"
  ],
  "recommended_next_action": "Coordinator to call customer and discuss if their concerns can be addressed via our available Botox or Filler consultations, or recommend trusted external partners."
}
```
