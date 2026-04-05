"""DeepBlue tool selection eval prompts.

Manual test harness — run via POST /v1/deepblue/eval-run to verify
Claude picks the right tool for common prompts. Not an automated gate,
just a sanity check after changes.
"""

EVAL_PROMPTS = [
    # Fuzzy search
    {
        "id": "find_by_address_fragment",
        "prompt": "find the account at Walili",
        "expected_tools": ["find_customer", "find_property"],
        "must_not_contain": ["I need", "can you give me"],
    },
    {
        "id": "find_by_partial_name",
        "prompt": "pull up Keith Lew's account",
        "expected_tools": ["find_customer"],
    },
    # Dosing (deterministic calculator must be used)
    {
        "id": "dosing_low_ph",
        "prompt": "pH is 6.8 on a 45000 gallon pool, what do I add?",
        "expected_tools": ["chemical_dosing_calculator"],
    },
    # Equipment lookup
    {
        "id": "equipment_lookup",
        "prompt": "what equipment is on the Pinebrook pool?",
        "expected_tools_any": ["find_property", "get_equipment"],
    },
    # Parts
    {
        "id": "parts_search",
        "prompt": "find replacement parts for a Polaris 280 booster",
        "expected_tools": ["find_replacement_parts"],
    },
    # Billing (merged tool)
    {
        "id": "invoices_for_customer",
        "prompt": "show me open invoices for Sierra Oaks",
        "expected_tools_any": ["find_customer", "get_billing_documents"],
    },
    {
        "id": "estimates_for_customer",
        "prompt": "any pending estimates for Lew?",
        "expected_tools_any": ["find_customer", "get_billing_documents"],
    },
    # Write actions
    {
        "id": "add_equipment",
        "prompt": "add a Polaris PB4-60 booster pump to the Walili pool",
        "expected_tools": ["find_property", "add_equipment_to_pool"],
    },
    {
        "id": "log_reading",
        "prompt": "log pH 7.4, FC 2.5, alkalinity 100 for the Pinebrook pool",
        "expected_tools_any": ["find_property", "log_chemical_reading"],
    },
    # Broadcasts
    {
        "id": "broadcast_test_send",
        "prompt": "draft an email about our new mailing address and send me a test",
        "expected_tools": ["draft_broadcast_email"],
    },
    # Cases/jobs
    {
        "id": "open_jobs",
        "prompt": "what jobs do I have open?",
        "expected_tools": ["get_open_jobs"],
    },
    # Routes
    {
        "id": "routes_today",
        "prompt": "what routes are running today?",
        "expected_tools": ["get_routes_today"],
    },
    # Off-topic (should decline)
    {
        "id": "off_topic",
        "prompt": "write me a poem about cats",
        "expected_off_topic": True,
    },
    # Novel query requiring query_database
    {
        "id": "meta_tool_query",
        "prompt": "which customers have no equipment on file?",
        "expected_tools_any": ["query_database"],
    },
    # Org info (should use baseline context, no tool needed)
    {
        "id": "org_info_from_context",
        "prompt": "what's our mailing address?",
        "expected_no_tools_required": True,
    },
]
