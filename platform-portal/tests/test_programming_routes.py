from portal import create_app
from portal.programming import programming_bp

EXPECTED_PROGRAMMING_ROUTES = {
    ("programming.bulk_preview", "/programming/blocks/<int:block_id>/bulk-preview", "POST"),
    ("programming.bulk_apply", "/programming/blocks/<int:block_id>/bulk-apply", "POST"),
    ("programming.copy_session_forward_preview", "/programming/sessions/<int:session_id>/copy-forward-preview", "POST"),
    ("programming.copy_session_forward", "/programming/sessions/<int:session_id>/copy-forward", "POST"),
    (
        "programming.revise_block",
        "/programming/blocks/<int:block_id>/revise",
        "POST",
    ),
    (
        "programming.activate_block",
        "/programming/blocks/<int:block_id>/activate",
        "POST",
    ),
    ("programming.archive_block", "/programming/blocks/<int:block_id>/archive", "POST"),
    ("programming.archive_block", "/programming/blocks/<int:block_id>/close", "POST"),
    ("programming.athlete_program", "/athletes/<int:athlete_id>/programming", "GET"),
    ("programming.block", "/programming/blocks/<int:block_id>", "GET"),
    ("programming.create_block", "/programming/blocks", "POST"),
    (
        "programming.create_prescription",
        "/programming/sessions/<int:session_id>/prescriptions",
        "POST",
    ),
    (
        "programming.create_lift_slot",
        "/programming/sessions/<int:session_id>/lift-slots",
        "POST",
    ),
    ("programming.create_session", "/programming/weeks/<int:week_id>/sessions", "POST"),
    ("programming.move_session", "/programming/sessions/<int:session_id>/move", "POST"),
    ("programming.create_week", "/programming/blocks/<int:block_id>/weeks", "POST"),
    ("programming.edit_block", "/programming/blocks/<int:block_id>/edit", "POST"),
    ("programming.edit_week", "/programming/weeks/<int:week_id>/edit", "POST"),
    (
        "programming.delete_draft_block",
        "/programming/blocks/<int:block_id>/delete",
        "POST",
    ),
    (
        "programming.delete_session",
        "/programming/sessions/<int:session_id>/delete",
        "POST",
    ),
    (
        "programming.duplicate_block",
        "/programming/blocks/<int:block_id>/duplicate",
        "POST",
    ),
    (
        "programming.duplicate_session",
        "/programming/sessions/<int:session_id>/duplicate",
        "POST",
    ),
    (
        "programming.duplicate_week",
        "/programming/weeks/<int:week_id>/duplicate",
        "POST",
    ),
    (
        "programming.delete_week",
        "/programming/weeks/<int:week_id>/delete",
        "POST",
    ),
    (
        "programming.reorder_week",
        "/programming/weeks/<int:week_id>/reorder",
        "POST",
    ),
    (
        "programming.extend_block",
        "/programming/blocks/<int:block_id>/extend",
        "POST",
    ),
    ("programming.index", "/programming", "GET"),
    (
        "programming.insert_session_after",
        "/programming/sessions/<int:session_id>/insert-after",
        "POST",
    ),
    (
        "programming.insert_session_before",
        "/programming/sessions/<int:session_id>/insert-before",
        "POST",
    ),
    (
        "programming.update_prescription",
        "/programming/prescriptions/<int:prescription_id>",
        "POST",
    ),
    (
        "programming.delete_prescription",
        "/programming/prescriptions/<int:prescription_id>/delete",
        "POST",
    ),
    ("programming.session", "/programming/sessions/<int:session_id>", "GET"),
    ("programming.week", "/programming/weeks/<int:week_id>", "GET"),
    ("programming.create_warmup_protocol", "/programming/sessions/<int:session_id>/warmup-protocols", "POST"),
    ("programming.assign_warmup", "/programming/sessions/<int:session_id>/warmup-assignments", "POST"),
    ("programming.accept_warmup_candidate", "/programming/sessions/<int:session_id>/warmup-candidates/accept", "POST"),
    ("programming.override_warmup_candidate", "/programming/sessions/<int:session_id>/warmup-candidates/override", "POST"),
    ("programming.override_warmup", "/programming/sessions/<int:session_id>/warmup-overrides", "POST"),
    (
        "programming.update_lift_slot",
        "/programming/lift-slots/<int:slot_id>",
        "POST",
    ),
    (
        "programming.delete_lift_slot",
        "/programming/lift-slots/<int:slot_id>/delete",
        "POST",
    ),
}


def test_programming_blueprint_compatibility_export():
    assert programming_bp.name == "programming"


def test_all_programming_routes_keep_their_endpoints_urls_and_methods():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    actual = {
        (rule.endpoint, rule.rule, method)
        for rule in app.url_map.iter_rules()
        if rule.endpoint.startswith("programming.")
        for method in rule.methods - {"HEAD", "OPTIONS"}
    }
    assert actual == EXPECTED_PROGRAMMING_ROUTES
