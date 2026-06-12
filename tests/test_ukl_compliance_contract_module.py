from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ukl_compliance_contract_module as module


def test_current_mvp_must_not_claim_full_ukl_compliance():
    assert module.is_fully_compliant() is False


def test_missing_mandatory_artifacts_remain_visible():
    gaps = {contract.code for contract in module.blocking_gaps()}
    assert {
        "HOLDER_H01",
        "USER_AV01",
        "USER_T01",
        "USER_AB01",
        "PROCESS_AS4",
        "PROCESS_QUITTUNGEN",
    }.issubset(gaps)


def test_holder_and_user_roles_are_both_tracked():
    assert module.contracts_by_role("HALTER")
    assert module.contracts_by_role("NUTZER")
