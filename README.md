# ClauseGuard

ClauseGuard is a natural-language policy authorization primitive built on GenLayer.

It lets an owner define a human-readable policy and lets callers submit proposed actions, justification, evidence, and a caller-scoped reference. GenLayer validators independently interpret the policy and proposed action, then reach consensus on one of three outcomes:

- `ALLOW`
- `DENY`
- `REVIEW`

Successful decisions are persisted onchain together with the policy version, policy snapshot, action, evidence, submitter, reference, and deterministic commitment.

## Why ClauseGuard

Traditional smart contracts are excellent at enforcing deterministic conditions such as numeric limits, allowlists, timestamps, and signatures.

They are much weaker when authorization depends on interpreting natural-language policy.

ClauseGuard targets rules such as:

- Treasury funds may be used for security audits and infrastructure.
- Payments above a certain threshold require governance approval.
- Funds may not be used for cryptocurrency speculation.
- Funds may not be transferred to personal wallets.
- Ambiguous actions should be escalated for review.

These policies are understandable to humans but are difficult to encode completely as deterministic smart-contract logic.

ClauseGuard uses GenLayer consensus to interpret those policies directly.

## How It Works

ClauseGuard has two main flows.

### 1. Configure Policy

The contract owner sets a natural-language policy with `set_policy(policy)`.

Each successful update increments `policy_version`.

Example policy:

```text
Treasury funds may be used for security audits, infrastructure, and contributor payments.
Individual payments above $10000 require explicit governance approval.
Funds may not be used for cryptocurrency speculation or transfers to personal wallets.
```

### 2. Evaluate a Proposed Action

A caller submits:

- Proposed action
- Justification
- Evidence
- Caller-scoped reference

Example:

```text
Action:
Pay SecureLabs $5000 for a protocol security audit.

Justification:
The payment is for a security audit permitted by the treasury policy.

Evidence:
SecureLabs submitted an audit engagement letter for the protocol.

Reference:
bradbury-allow-002
```

The contract builds a deterministic prompt from the current policy and action data.

The leader evaluates the request. Validators independently evaluate the same request and compare the verdict.

```python
gl.vm.run_nondet(
    leader_fn,
    validator_fn,
)
```

## Verdicts

ClauseGuard accepts only three verdicts.

### ALLOW

The proposed action is clearly authorized by the policy.

### DENY

The proposed action clearly violates the policy or falls outside the allowed scope.

### REVIEW

The policy or submitted information is insufficient to safely determine authorization.

## Strict Consensus Output

ClauseGuard accepts only this exact result schema:

```json
{
  "verdict": "ALLOW"
}
```

The contract validates:

- Top-level result type
- Exact result keys
- Verdict type
- Allowed verdict values

Unexpected or malformed model output is rejected.

## Policy Versioning

Every policy update increments the policy version.

Each successful authorization decision stores:

- The policy version used
- A full snapshot of the policy at the time of evaluation

This means historical decisions remain tied to the exact policy that governed them even after the owner updates the active policy.

## Persistent Decisions

Successful evaluations store:

- Decision ID
- Policy version
- Policy snapshot
- Action
- Justification
- Evidence
- Verdict
- Submitter
- Reference
- Commitment

Read methods include:

```text
get_policy()
get_decision_count()
get_decision(decision_id)
is_reference_used(submitter, reference)
```

## Caller-Scoped References

Every evaluation includes a caller-supplied reference.

References are unique per submitter.

Example:

```text
Alice + payment-001 = allowed
Alice + payment-001 again = rejected
Bob + payment-001 = allowed
```

This prevents accidental replay by the same caller without requiring global reference uniqueness.

## Deterministic Commitments

Every successful decision receives a deterministic Keccak-256 commitment.

The commitment binds:

- Submitter
- Policy version
- Policy snapshot
- Action
- Justification
- Evidence
- Reference

Changing any of these inputs changes the commitment.

This provides a deterministic fingerprint for the exact authorization request and policy context.

## Failure Safety

Failed evaluations do not partially mutate contract state.

If an evaluation fails:

- `decision_count` is not incremented.
- No decision is stored.
- The caller reference is not consumed.

## Bradbury Deployment

ClauseGuard is deployed on the GenLayer Bradbury testnet.

Contract address:

```text
0xFf8F7c9aa3cDdcF54a67880F653127C80C37E423
```

Deployment transaction:

```text
0xfcd893de2f7d48b8200d511cd90e489b27593973d0a6b1bd3bd3f9bf07944fca
```

Network:

```text
GenLayer Bradbury
```

RPC:

```text
https://rpc-bradbury.genlayer.com
```

The deployed contract was verified with:

```text
ping() -> clauseguard-v1
```

## Verified Bradbury ALLOW Decision

Reference:

```text
bradbury-allow-002
```

Action:

```text
Pay SecureLabs $5000 for a protocol security audit.
```

Result:

```text
ALLOW
```

Consensus status:

```text
ACCEPTED
AGREE
FINISHED_WITH_RETURN
```

Transaction:

```text
0x00262c76490be4e128db56125b42a8a39f4e19a5535204a94c65c97dcd876e7c
```

## Verified Bradbury DENY Decision

Reference:

```text
bradbury-deny-003
```

Action:

```text
Transfer $50 to a personal wallet.
```

The active policy explicitly prohibits transfers to personal wallets.

Result:

```text
DENY
```

All five validators agreed.

Consensus status:

```text
ACCEPTED
AGREE
FINISHED_WITH_RETURN
```

Transaction:

```text
0x9fca2d9cd6dc6813307f57c045e226795b97b1437caeb5e63dab0af679f0ecd9
```

## Reading From Bradbury

Check the contract:

```bash
genlayer call \
  0xFf8F7c9aa3cDdcF54a67880F653127C80C37E423 \
  ping \
  --rpc https://rpc-bradbury.genlayer.com
```

Read the active policy:

```bash
genlayer call \
  0xFf8F7c9aa3cDdcF54a67880F653127C80C37E423 \
  get_policy \
  --rpc https://rpc-bradbury.genlayer.com
```

Get the number of successful decisions:

```bash
genlayer call \
  0xFf8F7c9aa3cDdcF54a67880F653127C80C37E423 \
  get_decision_count \
  --rpc https://rpc-bradbury.genlayer.com
```

Read decision `0`:

```bash
genlayer call \
  0xFf8F7c9aa3cDdcF54a67880F653127C80C37E423 \
  get_decision \
  --rpc https://rpc-bradbury.genlayer.com \
  --args 0
```

## Tests

ClauseGuard uses `genlayer-test` direct-mode tests.

Run:

```bash
python3 -m py_compile contracts/clause_guard.py
gltest test/test_clause_guard.py -v
```

Current status:

```text
20 passed
```

The test suite covers:

- Contract health check
- Owner-only policy updates
- Policy version increments
- ALLOW persistence
- DENY persistence
- REVIEW persistence
- Historical policy snapshots
- Caller-scoped references
- Duplicate-reference rejection
- Same reference usage by different callers
- Policy-required enforcement
- Empty-input validation
- Strict LLM output schema validation
- Invalid verdict rejection
- Failed-evaluation storage safety
- Failed-evaluation reference safety
- Commitment format and persistence
- Policy-version-bound commitments

## Repository Structure

```text
clauseguard/
├── contracts/
│   └── clause_guard.py
├── test/
│   └── test_clause_guard.py
├── requirements.txt
├── LICENSE
└── README.md
```

The intelligent contract is located at:

```text
contracts/clause_guard.py
```

## Current Scope

ClauseGuard is designed as a reusable authorization primitive.

An integrating application can use ClauseGuard wherever a proposed action needs to be checked against a natural-language policy before proceeding.

Potential integrations include:

- DAO treasury authorization
- AI-agent action controls
- Grant spending policies
- Procurement workflows
- Compliance gates
- Operational spending controls
- Governance execution safeguards

ClauseGuard currently records authorization decisions. It does not automatically execute downstream transfers or protocol actions.

## Status

- Intelligent contract implemented
- 20 direct-mode tests passing
- Natural-language policy evaluation implemented
- ALLOW / DENY / REVIEW verdicts implemented
- Policy versioning implemented
- Historical policy snapshots implemented
- Caller-scoped references implemented
- Deterministic Keccak-256 commitments implemented
- Strict output validation implemented
- Failure-state safety tested
- Deployed on Bradbury
- Live ALLOW decision verified
- Live DENY decision verified with 5/5 validator agreement

## License

MIT
