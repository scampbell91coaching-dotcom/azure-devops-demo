from pathlib import Path

import pytest
from flask import render_template, render_template_string

from portal import create_app


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def app():
    return create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "LEGACY_STARTUP_INITIALIZATION": False,
        }
    )


@pytest.fixture
def client(app):
    return app.test_client()


def render_component(app, source):
    with app.test_request_context("/"):
        return render_template_string(
            "{% import 'design_system/components.html' as ds %}" + source
        )


def test_design_system_stylesheet_is_available(app, client):
    response = client.get("/static/css/design-system.css")

    assert response.status_code == 200
    assert response.mimetype == "text/css"
    assert b"--ts-color-brand-black" in response.data
    assert b"prefers-reduced-motion: reduce" in response.data
    assert b"--ts-workspace-bg" in response.data
    assert b".ts-context-bar" in response.data
    assert b".ts-workspace-grid" in response.data


def test_button_variants_disabled_and_loading_states_render(app):
    html = render_component(
        app,
        "{{ ds.button('Save', type='submit') }}"
        "{{ ds.button('Cancel', 'secondary', disabled=true) }}"
        "{{ ds.button('Working', loading=true) }}"
        "{{ ds.button('Remove', 'danger') }}",
    )

    assert 'class="ts-button ts-button--primary"' in html
    assert 'type="submit"' in html
    assert 'class="ts-button ts-button--secondary"' in html
    assert " disabled" in html
    assert 'aria-busy="true"' in html
    assert 'aria-busy="true"' in html and html.count(" disabled") == 2
    assert 'class="ts-button ts-button--danger"' in html


def test_icon_button_has_accessible_name_and_hidden_icon(app):
    html = render_component(app, "{{ ds.icon_button('Add athlete', '+') }}")

    assert 'aria-label="Add athlete"' in html
    assert '<span aria-hidden="true">+</span>' in html


def test_form_error_is_associated_with_native_input(app):
    html = render_component(
        app,
        "{{ ds.input_field('email', 'Email', help='Work address.', "
        "error='Enter a valid email.', required=true) }}",
    )

    assert '<label class="ts-field__label" for="email">' in html
    assert 'id="email" name="email" type="text"' in html
    assert 'aria-invalid="true"' in html
    assert 'aria-errormessage="email-error"' in html
    assert 'aria-describedby="email-error email-help"' in html
    assert 'id="email-help"' in html
    assert 'id="email-error"' in html
    assert " required" in html
    assert html.index('id="email-error"') < html.index('id="email-help"')


def test_field_id_can_differ_from_submission_name(app):
    html = render_component(
        app,
        "{{ ds.input_field('amount', 'Opening attempt', id='squat-amount') }}",
    )

    assert 'for="squat-amount"' in html
    assert 'id="squat-amount" name="amount"' in html


def test_error_summary_links_to_fields_and_can_receive_focus(app):
    html = render_component(
        app,
        "{{ ds.form_errors([('email', 'Enter an email'), "
        "('notes', 'Add coach notes')]) }}",
    )

    assert 'class="ts-error-summary" role="alert" tabindex="-1"' in html
    assert '<a href="#email">Enter an email</a>' in html
    assert '<a href="#notes">Add coach notes</a>' in html


def test_optional_feedback_copy_does_not_render_empty_paragraphs(app):
    html = render_component(
        app,
        "{{ ds.alert('Programme saved', status='success') }}"
        "{{ ds.empty_state('No check-ins', heading_level=2) }}",
    )

    assert "ts-alert__body" not in html
    assert "ts-empty-state__body" not in html
    assert '<h2 class="ts-empty-state__title">No check-ins</h2>' in html


def test_choices_remain_native_and_disabled(app):
    html = render_component(
        app,
        "{{ ds.choice('consent', 'I agree', disabled=true) }}"
        "{{ ds.choice('units', 'Kilograms', 'kg', 'radio', true) }}",
    )

    assert 'type="checkbox" disabled' in html
    assert 'type="radio" checked' in html


def test_alert_roles_match_urgency(app):
    html = render_component(
        app,
        "{{ ds.alert('Saved', 'Changes saved.', 'success') }}"
        "{{ ds.alert('Could not save', 'Try again.', 'danger') }}",
    )

    assert 'ts-alert--success" role="status" aria-live="polite"' in html
    assert 'ts-alert--danger" role="alert"' in html


def test_table_wrapper_and_loading_indicator_are_named(app):
    html = render_component(
        app,
        "{% call ds.table_wrapper('Athletes') %}<table></table>{% endcall %}"
        "{{ ds.skeleton('Loading athletes', 2) }}",
    )

    assert 'role="region" aria-label="Athletes" tabindex="0"' in html
    assert 'role="status" aria-label="Loading athletes" aria-busy="true"' in html
    assert html.count('class="ts-skeleton" aria-hidden="true"') == 2


def test_dialog_uses_native_element_and_accessible_relationships(app):
    html = render_component(
        app,
        "{% call ds.dialog('confirm-remove', 'Remove athlete', "
        "'This cannot be undone.') %}<p>Confirm the removal.</p>{% endcall %}",
    )

    assert '<dialog class="ts-dialog" id="confirm-remove"' in html
    assert 'aria-labelledby="confirm-remove-title"' in html
    assert 'aria-describedby="confirm-remove-description"' in html
    assert '<form method="dialog">' in html
    assert 'aria-label="Close dialog"' in html


def test_context_bar_preserves_term_value_relationships(app):
    html = render_component(
        app,
        "{{ ds.context_bar([('Athlete', 'Alex Morgan'), ('Week', '3 of 8')]) }}",
    )

    assert '<dl class="ts-context-bar" aria-label="Current workspace context">' in html
    assert '<dt class="ts-context-item__label">Athlete</dt>' in html
    assert '<dd class="ts-context-item__value">Alex Morgan</dd>' in html


def test_showcase_renders_all_foundational_sections(app):
    with app.test_request_context("/"):
        html = render_template("design_system/showcase.html")

    assert "Design System V1" in html
    assert "Forms" in html
    assert "Feedback and data" in html
    assert "Dark context" in html
    assert "Coach workspace" in html
    assert 'css/design-system.css' in html
    assert '<dialog class="ts-dialog"' not in html  # documented, not demo-opened
