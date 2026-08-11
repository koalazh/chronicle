from __future__ import annotations

from .base import CrisisResolutionContract, ResolutionContractError
from .nanjing_succession import NanjingSuccessionResolutionContract
from .shanhaiguan import ShanhaiGuanResolutionContract

_CONTRACTS: dict[tuple[str, int], CrisisResolutionContract] = {
    (
        NanjingSuccessionResolutionContract.id,
        NanjingSuccessionResolutionContract.version,
    ): NanjingSuccessionResolutionContract(),
    (ShanhaiGuanResolutionContract.id, ShanhaiGuanResolutionContract.version): ShanhaiGuanResolutionContract(),
}


def resolution_contract_registered(contract_id: str, version: int) -> bool:
    return (contract_id, version) in _CONTRACTS


def get_resolution_contract(contract_id: str, version: int) -> CrisisResolutionContract:
    try:
        return _CONTRACTS[(contract_id, version)]
    except KeyError as exc:
        raise ResolutionContractError(
            f"unknown Resolution Contract {contract_id}/v{version}"
        ) from exc
