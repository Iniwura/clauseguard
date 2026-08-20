from pathlib import Path
import json
import pytest


CONTRACT = Path(__file__).parent.parent / "contracts" / "clause_guard.py"


def mock_verdict(direct_vm, verdict):
    direct_vm.mock_llm(
        "Determine whether the proposed action is authorized by the policy.*",
        json.dumps({"verdict": verdict}),
    )


def test_ping(direct_deploy):
    contract = direct_deploy(CONTRACT)
    assert contract.ping() == "clauseguard-v1"


def test_owner_can_set_policy(direct_deploy):
    contract = direct_deploy(CONTRACT)

    result = contract.set_policy(
        "Treasury funds may be used for audits and infrastructure."
    )

    assert result["version"] == 1
    assert "audits" in result["policy"]

    stored = contract.get_policy()

    assert stored["version"] == 1
    assert "infrastructure" in stored["policy"]


def test_non_owner_cannot_set_policy(
    direct_deploy,
    direct_vm,
    direct_bob,
):
    contract = direct_deploy(CONTRACT)

    direct_vm.sender = direct_bob

    with pytest.raises(Exception):
        contract.set_policy(
            "Bob should not be able to replace the policy."
        )


def test_policy_version_increments(direct_deploy):
    contract = direct_deploy(CONTRACT)

    contract.set_policy("Policy version one.")
    contract.set_policy("Policy version two.")

    stored = contract.get_policy()

    assert stored["version"] == 2
    assert stored["policy"] == "Policy version two."


def test_allow_decision_is_stored(
    direct_deploy,
    direct_vm,
):
    contract = direct_deploy(CONTRACT)

    contract.set_policy(
        "Treasury funds may be used for security audits."
    )

    mock_verdict(direct_vm, "ALLOW")

    result = contract.evaluate_action(
        "Pay SecureLabs $5,000.",
        "Payment is for a protocol security audit.",
        "SecureLabs submitted an audit engagement letter.",
        "audit-payment-001",
    )

    assert result["decision_id"] == 0
    assert result["policy_version"] == 1
    assert result["verdict"] == "ALLOW"
    assert result["reference"] == "audit-payment-001"

    stored = contract.get_decision(0)

    assert stored["verdict"] == "ALLOW"
    assert stored["policy_version"] == 1
    assert stored["reference"] == "audit-payment-001"
    assert "security audit" in stored["policy"]


def test_deny_decision_is_stored(
    direct_deploy,
    direct_vm,
):
    contract = direct_deploy(CONTRACT)

    contract.set_policy(
        "Treasury funds may be used for audits. "
        "Funds may not be used for cryptocurrency speculation."
    )

    mock_verdict(direct_vm, "DENY")

    result = contract.evaluate_action(
        "Buy $2,000 of a speculative token.",
        "The agent expects the token price to increase.",
        "",
        "token-purchase-001",
    )

    assert result["verdict"] == "DENY"

    stored = contract.get_decision(0)
    assert stored["verdict"] == "DENY"


def test_review_decision_is_stored(
    direct_deploy,
    direct_vm,
):
    contract = direct_deploy(CONTRACT)

    contract.set_policy(
        "Treasury funds may be used for reasonable infrastructure."
    )

    mock_verdict(direct_vm, "REVIEW")

    result = contract.evaluate_action(
        "Pay $9,000 to an infrastructure consultant.",
        "",
        "",
        "consultant-001",
    )

    assert result["verdict"] == "REVIEW"


def test_policy_snapshot_is_preserved(
    direct_deploy,
    direct_vm,
):
    contract = direct_deploy(CONTRACT)

    contract.set_policy("Original policy.")

    mock_verdict(direct_vm, "ALLOW")

    contract.evaluate_action(
        "Action",
        "Justification",
        "Evidence",
        "snapshot-001",
    )

    contract.set_policy("Updated policy.")

    stored = contract.get_decision(0)

    assert stored["policy_version"] == 1
    assert stored["policy"] == "Original policy."

    current = contract.get_policy()

    assert current["version"] == 2
    assert current["policy"] == "Updated policy."


def test_reference_becomes_used_after_success(
    direct_deploy,
    direct_vm,
):
    contract = direct_deploy(CONTRACT)

    contract.set_policy("Allow approved infrastructure expenses.")

    mock_verdict(direct_vm, "ALLOW")

    module = __import__(
        contract.__class__.__module__,
        fromlist=["Address"],
    )

    sender = module.Address(direct_vm.sender)

    assert contract.is_reference_used(
        sender,
        "ref-001",
    ) is False

    contract.evaluate_action(
        "Buy server capacity.",
        "Needed for production.",
        "Infrastructure invoice.",
        "ref-001",
    )

    assert contract.is_reference_used(
        sender,
        "ref-001",
    ) is True


def test_duplicate_reference_is_rejected(
    direct_deploy,
    direct_vm,
):
    contract = direct_deploy(CONTRACT)

    contract.set_policy("Allow infrastructure.")

    mock_verdict(direct_vm, "ALLOW")

    contract.evaluate_action(
        "Action one",
        "",
        "",
        "duplicate-001",
    )

    with pytest.raises(Exception):
        contract.evaluate_action(
            "Action two",
            "",
            "",
            "duplicate-001",
        )


def test_same_reference_allowed_for_different_callers(
    direct_deploy,
    direct_vm,
    direct_alice,
    direct_bob,
):
    contract = direct_deploy(CONTRACT)

    contract.set_policy("Allow infrastructure.")

    mock_verdict(direct_vm, "ALLOW")

    direct_vm.sender = direct_alice

    contract.evaluate_action(
        "Alice action",
        "",
        "",
        "shared-ref",
    )

    direct_vm.sender = direct_bob

    contract.evaluate_action(
        "Bob action",
        "",
        "",
        "shared-ref",
    )

    assert contract.get_decision_count() == 2


def test_policy_required_before_evaluation(direct_deploy):
    contract = direct_deploy(CONTRACT)

    with pytest.raises(Exception):
        contract.evaluate_action(
            "Action",
            "",
            "",
            "ref",
        )


def test_empty_policy_rejected(direct_deploy):
    contract = direct_deploy(CONTRACT)

    with pytest.raises(Exception):
        contract.set_policy("")


def test_empty_action_rejected(direct_deploy):
    contract = direct_deploy(CONTRACT)

    contract.set_policy("Policy")

    with pytest.raises(Exception):
        contract.evaluate_action(
            "",
            "",
            "",
            "ref",
        )


def test_empty_reference_rejected(direct_deploy):
    contract = direct_deploy(CONTRACT)

    contract.set_policy("Policy")

    with pytest.raises(Exception):
        contract.evaluate_action(
            "Action",
            "",
            "",
            "",
        )


def test_invalid_llm_schema_rejected(
    direct_deploy,
    direct_vm,
):
    contract = direct_deploy(CONTRACT)

    contract.set_policy("Policy")

    direct_vm.mock_llm(
        "Determine whether the proposed action is authorized by the policy.*",
        json.dumps({
            "verdict": "ALLOW",
            "reasoning": "extra field",
        }),
    )

    with pytest.raises(Exception):
        contract.evaluate_action(
            "Action",
            "",
            "",
            "bad-schema",
        )


def test_invalid_verdict_rejected(
    direct_deploy,
    direct_vm,
):
    contract = direct_deploy(CONTRACT)

    contract.set_policy("Policy")

    mock_verdict(direct_vm, "MAYBE")

    with pytest.raises(Exception):
        contract.evaluate_action(
            "Action",
            "",
            "",
            "bad-verdict",
        )


def test_failed_evaluation_does_not_mutate_state(
    direct_deploy,
    direct_vm,
):
    contract = direct_deploy(CONTRACT)

    contract.set_policy("Policy")

    module = __import__(
        contract.__class__.__module__,
        fromlist=["Address"],
    )

    sender = module.Address(direct_vm.sender)

    direct_vm.mock_llm(
        "Determine whether the proposed action is authorized by the policy.*",
        "not valid json",
    )

    assert contract.get_decision_count() == 0

    with pytest.raises(Exception):
        contract.evaluate_action(
            "Action",
            "",
            "",
            "failed-ref",
        )

    assert contract.get_decision_count() == 0

    assert contract.is_reference_used(
        sender,
        "failed-ref",
    ) is False


def test_commitment_is_stored_and_hex(
    direct_deploy,
    direct_vm,
):
    contract = direct_deploy(CONTRACT)

    contract.set_policy("Policy")

    mock_verdict(direct_vm, "ALLOW")

    result = contract.evaluate_action(
        "Action",
        "Justification",
        "Evidence",
        "commitment-001",
    )

    commitment = result["commitment"]

    assert isinstance(commitment, str)
    assert len(commitment) == 64
    int(commitment, 16)

    stored = contract.get_decision(0)

    assert stored["commitment"] == commitment


def test_commitment_changes_with_policy_version(
    direct_deploy,
    direct_vm,
):
    contract = direct_deploy(CONTRACT)

    module = __import__(
        contract.__class__.__module__,
        fromlist=["build_commitment", "Address", "u256"],
    )

    sender = module.Address(direct_vm.sender)

    first = module.build_commitment(
        sender,
        module.u256(1),
        "Policy one",
        "Action",
        "",
        "",
        "ref",
    )

    second = module.build_commitment(
        sender,
        module.u256(2),
        "Policy two",
        "Action",
        "",
        "",
        "ref",
    )

    assert first != second
