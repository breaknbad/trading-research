"""
Authenticated Coinbase Advanced Trade API client using JWT (ES256).

Requires COINBASE_API_KEY and COINBASE_API_SECRET in .env.
"""

import json
import time
import uuid
import logging
from typing import Any, Dict, Optional

import jwt
import requests
from cryptography.hazmat.primitives import serialization
from dotenv import load_dotenv
import os

load_dotenv()

logger = logging.getLogger(__name__)

API_HOST = "api.coinbase.com"
BASE_URL = f"https://{API_HOST}"


class CoinbaseAuthClient:
    """Authenticated client for Coinbase Advanced Trade API."""

    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        self.api_key = api_key or os.getenv("COINBASE_API_KEY")
        self.api_secret = api_secret or os.getenv("COINBASE_API_SECRET")
        if not self.api_key or not self.api_secret:
            raise ValueError("COINBASE_API_KEY and COINBASE_API_SECRET must be set")

        # Parse the EC private key
        secret = self.api_secret
        if not secret.startswith("-----"):
            secret = f"-----BEGIN EC PRIVATE KEY-----\n{secret}\n-----END EC PRIVATE KEY-----"
        self._private_key = serialization.load_pem_private_key(
            secret.encode(), password=None
        )

    def _build_jwt(self, method: str, path: str) -> str:
        """Build a signed JWT for the given request."""
        now = int(time.time())
        uri = f"{method} {API_HOST}{path}"

        payload = {
            "sub": self.api_key,
            "iss": "cdp",
            "aud": ["retail_rest_api_proxy"],
            "nbf": now,
            "exp": now + 120,
            "uri": uri,
        }

        headers = {
            "kid": self.api_key,
            "nonce": uuid.uuid4().hex,
            "typ": "JWT",
        }

        return jwt.encode(payload, self._private_key, algorithm="ES256", headers=headers)

    def _request(self, method: str, path: str, params: Optional[Dict] = None,
                 body: Optional[Dict] = None) -> Dict[str, Any]:
        """Make an authenticated request."""
        token = self._build_jwt(method, path)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        url = f"{BASE_URL}{path}"

        try:
            resp = requests.request(
                method, url, headers=headers, params=params,
                json=body, timeout=30
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            logger.error("API request failed: %s %s — %s", method, path, exc)
            if hasattr(exc, 'response') and exc.response is not None:
                logger.error("Response body: %s", exc.response.text)
            raise

    # ── Account endpoints ──

    def get_accounts(self, limit: int = 49, cursor: str = "") -> Dict[str, Any]:
        """List trading accounts."""
        params = {"limit": str(limit)}
        if cursor:
            params["cursor"] = cursor
        return self._request("GET", "/api/v3/brokerage/accounts", params=params)

    # ── Product endpoints ──

    def get_product(self, product_id: str) -> Dict[str, Any]:
        """Get details for a single product (e.g. BTC-USD)."""
        return self._request("GET", f"/api/v3/brokerage/market/products/{product_id}")

    # ── Order endpoints ──

    def place_order(
        self,
        product_id: str,
        side: str,
        order_type: str = "MARKET",
        base_size: Optional[str] = None,
        quote_size: Optional[str] = None,
        limit_price: Optional[str] = None,
        client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Place a new order.

        Args:
            product_id: e.g. "BTC-USD"
            side: "BUY" or "SELL"
            order_type: "MARKET" or "LIMIT"
            base_size: Amount of base currency (e.g. "0.001" BTC)
            quote_size: Amount of quote currency (e.g. "100" USD) — market buys only
            limit_price: Required for limit orders
            client_order_id: Optional idempotency key
        """
        if client_order_id is None:
            client_order_id = uuid.uuid4().hex

        order_config = {}
        if order_type == "MARKET":
            if side == "BUY" and quote_size:
                order_config = {"market_market_ioc": {"quote_size": quote_size}}
            elif base_size:
                order_config = {"market_market_ioc": {"base_size": base_size}}
        elif order_type == "LIMIT" and limit_price and base_size:
            order_config = {
                "limit_limit_gtc": {
                    "base_size": base_size,
                    "limit_price": limit_price,
                }
            }

        body = {
            "client_order_id": client_order_id,
            "product_id": product_id,
            "side": side,
            "order_configuration": order_config,
        }

        return self._request("POST", "/api/v3/brokerage/orders", body=body)

    def get_order(self, order_id: str) -> Dict[str, Any]:
        """Get details for a specific order."""
        return self._request("GET", f"/api/v3/brokerage/orders/historical/{order_id}")

    def list_orders(self, product_id: Optional[str] = None,
                    order_status: Optional[str] = None,
                    limit: int = 100) -> Dict[str, Any]:
        """List orders with optional filters."""
        params = {"limit": str(limit)}
        if product_id:
            params["product_id"] = product_id
        if order_status:
            params["order_status"] = order_status
        return self._request("GET", "/api/v3/brokerage/orders/historical/batch", params=params)
