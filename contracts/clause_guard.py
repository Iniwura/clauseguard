# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import *
from genlayer.py.keccak import Keccak256
import json
import typing


MAX_POLICY_LENGTH = 8000
MAX_ACTION_LENGTH = 2000
MAX_JUSTIFICATION_LENGTH = 4000
MAX_EVIDENCE_LENGTH = 12000
MAX_REFERENCE_LENGTH = 128


def parse_decision(raw) -> str:
    if isinstance(raw, str):
        data = json.loads(raw)
    elif isinstance(raw, dict):
        data = raw
    else:
        raise ValueError("decision must be JSON text or an object")

    if not isinstance(data, dict):
        raise ValueError("decision must be an object")

    if set(data.keys()) != {"verdict"}:
        raise ValueError("invalid decision schema")

    verdict = data["verdict"]

    if not isinstance(verdict, str):
        raise ValueError("verdict must be a string")

    if verdict not in ("ALLOW", "DENY", "REVIEW"):
        raise ValueError("invalid verdict")

    return verdict


def build_commitment(
    submitter: Address,
    policy_version: u256,
    policy: str,
    action: str,
    justification: str,
    evidence: str,
    reference: str,
) -> str:
    payload = {
        "submitter": str(submitter),
        "policy_version": int(policy_version),
        "policy": policy,
        "action": action,
        "justification": justification,
        "evidence": evidence,
        "reference": reference,
    }

    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    )

    return Keccak256(canonical.encode("utf-8")).hexdigest()


@allow_storage
class Decision:
    policy_version: u256
    policy_snapshot: str
    action: str
    justification: str
    evidence: str
    verdict: str
    submitter: Address
    reference: str
    commitment: str


class ClauseGuard(gl.Contract):
    owner: Address
    policy: str
    policy_version: u256

    decision_count: u256
    decisions: TreeMap[u256, Decision]

    used_references: TreeMap[str, bool]

    def __init__(self):
        self.owner = gl.message.sender_address
        self.policy = ""
        self.policy_version = u256(0)
        self.decision_count = u256(0)

    def _reference_key(
        self,
        submitter: Address,
        reference: str,
    ) -> str:
        return submitter.as_hex + ":" + reference

    @gl.public.view
    def ping(self) -> str:
        return "clauseguard-v1"

    @gl.public.view
    def get_policy(self) -> typing.Any:
        return {
            "owner": str(self.owner),
            "version": int(self.policy_version),
            "policy": self.policy,
        }

    @gl.public.write
    def set_policy(self, policy: str) -> typing.Any:
        if gl.message.sender_address != self.owner:
            raise gl.vm.UserError("only owner can update policy")

        if not isinstance(policy, str) or not policy.strip():
            raise gl.vm.UserError("policy is required")

        if len(policy) > MAX_POLICY_LENGTH:
            raise gl.vm.UserError("policy is too long")

        self.policy = policy
        self.policy_version += u256(1)

        return {
            "version": int(self.policy_version),
            "policy": self.policy,
        }

    @gl.public.write
    def evaluate_action(
        self,
        action: str,
        justification: str,
        evidence: str,
        reference: str,
    ) -> typing.Any:

        if self.policy_version == u256(0):
            raise gl.vm.UserError("policy has not been configured")

        if not isinstance(action, str) or not action.strip():
            raise gl.vm.UserError("action is required")

        if len(action) > MAX_ACTION_LENGTH:
            raise gl.vm.UserError("action is too long")

        if not isinstance(justification, str):
            raise gl.vm.UserError("justification must be a string")

        if len(justification) > MAX_JUSTIFICATION_LENGTH:
            raise gl.vm.UserError("justification is too long")

        if not isinstance(evidence, str):
            raise gl.vm.UserError("evidence must be a string")

        if len(evidence) > MAX_EVIDENCE_LENGTH:
            raise gl.vm.UserError("evidence is too long")

        if not isinstance(reference, str) or not reference.strip():
            raise gl.vm.UserError("reference is required")

        if len(reference) > MAX_REFERENCE_LENGTH:
            raise gl.vm.UserError("reference is too long")

        sender = gl.message.sender_address
        reference_key = self._reference_key(
            sender,
            reference,
        )

        if self.used_references.get(reference_key, False):
            raise gl.vm.UserError("reference already used by caller")

        policy_snapshot = self.policy
        policy_version = self.policy_version

        prompt = (
            "Determine whether the proposed action is authorized by the policy.\n\n"
            "POLICY:\n"
            + policy_snapshot
            + "\n\nPROPOSED ACTION:\n"
            + action
            + "\n\nJUSTIFICATION:\n"
            + justification
            + "\n\nEVIDENCE:\n"
            + evidence
            + "\n\nReturn JSON only in exactly this form:\n"
            '{"verdict":"ALLOW"}\n\n'
            "Allowed verdicts are ALLOW, DENY, or REVIEW.\n"
            "ALLOW means the action is clearly authorized by the policy.\n"
            "DENY means the action clearly violates or falls outside the policy.\n"
            "REVIEW means the policy or supplied information is insufficient "
            "to determine authorization safely."
        )

        def leader_fn():
            raw = gl.nondet.exec_prompt(prompt)
            return parse_decision(raw)

        def validator_fn(leader_result):
            if not isinstance(leader_result, gl.vm.Return):
                return False

            try:
                raw = gl.nondet.exec_prompt(prompt)
                validator_verdict = parse_decision(raw)
            except Exception:
                return False

            return leader_result.calldata == validator_verdict

        verdict = gl.vm.run_nondet(
            leader_fn,
            validator_fn,
        )

        commitment = build_commitment(
            sender,
            policy_version,
            policy_snapshot,
            action,
            justification,
            evidence,
            reference,
        )

        decision_id = self.decision_count

        decision = Decision()
        decision.policy_version = policy_version
        decision.policy_snapshot = policy_snapshot
        decision.action = action
        decision.justification = justification
        decision.evidence = evidence
        decision.verdict = verdict
        decision.submitter = sender
        decision.reference = reference
        decision.commitment = commitment

        self.decisions[decision_id] = decision
        self.used_references[reference_key] = True
        self.decision_count += u256(1)

        return {
            "decision_id": int(decision_id),
            "policy_version": int(policy_version),
            "verdict": verdict,
            "reference": reference,
            "commitment": commitment,
        }

    @gl.public.view
    def get_decision_count(self) -> u256:
        return self.decision_count

    @gl.public.view
    def get_decision(
        self,
        decision_id: u256,
    ) -> typing.Any:
        if decision_id >= self.decision_count:
            raise gl.vm.UserError("decision does not exist")

        decision = self.decisions[decision_id]

        return {
            "id": int(decision_id),
            "policy_version": int(decision.policy_version),
            "policy": decision.policy_snapshot,
            "action": decision.action,
            "justification": decision.justification,
            "evidence": decision.evidence,
            "verdict": decision.verdict,
            "submitter": str(decision.submitter),
            "reference": decision.reference,
            "commitment": decision.commitment,
        }

    @gl.public.view
    def is_reference_used(
        self,
        submitter: Address,
        reference: str,
    ) -> bool:
        return self.used_references.get(
            self._reference_key(submitter, reference),
            False,
        )
