"""Helper fetchers for auto_balance API integrations."""
from __future__ import annotations

import json
import os
from decimal import Decimal
from typing import Any, Callable, Optional
from urllib import request


DEFAULT_BSC_ENDPOINT = os.getenv("BSC_ENDPOINT")
DEFAULT_ETH_ENDPOINT = os.getenv("ETH_ENDPOINT")


def fetch_wallet_balance(address: str, api_key: str | None = None, value: str | None = None) -> Decimal:
    """Simple example fetcher that just echoes the provided value."""
    if value is not None:
        return Decimal(value)
    return Decimal("0")


def fetch_bnb_balance_on_bsc(
    address: str,
    api_key: str | None = None,
    endpoint: str | None = None,
    timeout: int = 10,
    opener: Optional[Callable[..., Any]] = None,
) -> Decimal:
    """Fetch the BNB balance on BSC via an Infura (or compatible) JSON-RPC endpoint."""
    return _fetch_bsc_balance(
        address=address,
        api_key=api_key,
        endpoint=endpoint,
        timeout=timeout,
        opener=opener,
        rpc_method="eth_getBalance",
        decimals=18,
    )


def fetch_erc20_balance_on_bsc(
    address: str,
    contract: str,
    decimals: int,
    api_key: str | None = None,
    endpoint: str | None = None,
    timeout: int = 10,
    opener: Optional[Callable[..., Any]] = None,
) -> Decimal:
    if not contract:
        raise ValueError("contract address is required")

    padded_addr = address.lower().replace("0x", "").rjust(64, "0")
    data_field = "0x70a08231" + padded_addr

    return _fetch_bsc_balance(
        address=contract,
        api_key=api_key,
        endpoint=endpoint,
        timeout=timeout,
        opener=opener,
        rpc_method="eth_call",
        params=[{"to": contract, "data": data_field}, "latest"],
        decimals=decimals,
    )


def fetch_usdt_balance_on_bsc(**kwargs) -> Decimal:
    return fetch_erc20_balance_on_bsc(
        contract="0x55d398326f99059fF775485246999027B3197955",
        decimals=18,
        **kwargs,
    )


def fetch_usdc_balance_on_bsc(**kwargs) -> Decimal:
    return fetch_erc20_balance_on_bsc(
        contract="0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d",
        decimals=18,
        **kwargs,
    )


def fetch_eth_balance_on_ethereum(
    address: str,
    api_key: str | None = None,
    endpoint: str | None = None,
    timeout: int = 10,
    opener: Optional[Callable[..., Any]] = None,
) -> Decimal:
    """Fetch the ETH balance on Ethereum via a JSON-RPC endpoint."""
    return _fetch_eth_balance(
        address=address,
        api_key=api_key,
        endpoint=endpoint,
        timeout=timeout,
        opener=opener,
        rpc_method="eth_getBalance",
        decimals=18,
    )


def fetch_erc20_balance_on_ethereum(
    address: str,
    contract: str,
    decimals: int,
    api_key: str | None = None,
    endpoint: str | None = None,
    timeout: int = 10,
    opener: Optional[Callable[..., Any]] = None,
) -> Decimal:
    """Fetch an ERC-20 token balance on Ethereum."""
    if not contract:
        raise ValueError("contract address is required")

    padded_addr = address.lower().replace("0x", "").rjust(64, "0")
    data_field = "0x70a08231" + padded_addr

    return _fetch_eth_balance(
        address=contract,
        api_key=api_key,
        endpoint=endpoint,
        timeout=timeout,
        opener=opener,
        rpc_method="eth_call",
        params=[{"to": contract, "data": data_field}, "latest"],
        decimals=decimals,
    )


def fetch_usdt_balance_on_ethereum(**kwargs) -> Decimal:
    return fetch_erc20_balance_on_ethereum(
        contract="0xdAC17F958D2ee523a2206206994597C13D831ec7",
        decimals=6,
        **kwargs,
    )


def fetch_usdc_balance_on_ethereum(**kwargs) -> Decimal:
    return fetch_erc20_balance_on_ethereum(
        contract="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eb48",
        decimals=6,
        **kwargs,
    )


def _fetch_bsc_balance(
    address: str,
    api_key: Optional[str],
    endpoint: Optional[str],
    timeout: int,
    opener: Optional[Callable[..., Any]],
    rpc_method: str,
    decimals: int,
    params: Optional[list] = None,
) -> Decimal:
    if not address:
        raise ValueError("address is required")

    url = endpoint or DEFAULT_BSC_ENDPOINT
    if not url:
        if api_key:
            url = f"https://bsc-mainnet.infura.io/v3/{api_key}"
        else:
            raise ValueError("Provide BSC_ENDPOINT env, endpoint, or api_key")
    payload = {
        "jsonrpc": "2.0",
        "method": rpc_method,
        "params": params or [address, "latest"],
        "id": 1,
    }

    opener_fn = opener or request.urlopen
    req = request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
    with opener_fn(req, timeout=timeout) as response:
        raw = response.read()

    data = json.loads(raw.decode("utf-8"))
    if "error" in data:
        raise ValueError(f"RPC error: {data['error']}")

    result = data.get("result")
    if not isinstance(result, str):
        raise ValueError("Missing balance result in RPC response")

    wei_value = int(result, 16)
    return Decimal(wei_value) / Decimal(f"1e{decimals}")


def _fetch_eth_balance(
    address: str,
    api_key: Optional[str],
    endpoint: Optional[str],
    timeout: int,
    opener: Optional[Callable[..., Any]],
    rpc_method: str,
    decimals: int,
    params: Optional[list] = None,
) -> Decimal:
    if not address:
        raise ValueError("address is required")

    url = endpoint or DEFAULT_ETH_ENDPOINT
    if not url:
        if api_key:
            url = f"https://mainnet.infura.io/v3/{api_key}"
        else:
            raise ValueError("Provide ETH_ENDPOINT env, endpoint, or api_key")
    payload = {
        "jsonrpc": "2.0",
        "method": rpc_method,
        "params": params or [address, "latest"],
        "id": 1,
    }

    opener_fn = opener or request.urlopen
    req = request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
    with opener_fn(req, timeout=timeout) as response:
        raw = response.read()

    data = json.loads(raw.decode("utf-8"))
    if "error" in data:
        raise ValueError(f"RPC error: {data['error']}")

    result = data.get("result")
    if not isinstance(result, str):
        raise ValueError("Missing balance result in RPC response")

    wei_value = int(result, 16)
    return Decimal(wei_value) / Decimal(f"1e{decimals}")
