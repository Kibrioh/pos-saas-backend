from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

from flask import current_app


class IntegrationNotConfigured(RuntimeError):
    """Raised when the deployment has no adapter for an integration yet."""


@dataclass(frozen=True)
class PaymentIntentRequest:
    tenant_id: int
    branch_id: int
    amount: Decimal
    currency: str
    idempotency_key: str
    reference: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PaymentIntentResult:
    provider_reference: str
    status: str
    redirect_url: str | None = None
    client_data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FiscalSubmissionResult:
    status: str
    provider_reference: str | None = None
    invoice_number: str | None = None
    receipt_signature: str | None = None
    response: dict[str, Any] = field(default_factory=dict)


class PaymentProvider(Protocol):
    provider_code: str

    def create_intent(self, request: PaymentIntentRequest) -> PaymentIntentResult: ...
    def get_intent(self, provider_reference: str) -> PaymentIntentResult: ...
    def refund(self, provider_reference: str, amount: Decimal, idempotency_key: str) -> dict[str, Any]: ...


class EInvoiceProvider(Protocol):
    provider_code: str

    def submit_invoice(self, document: dict[str, Any], idempotency_key: str) -> FiscalSubmissionResult: ...
    def get_invoice_status(self, provider_reference: str) -> FiscalSubmissionResult: ...


class BillingProvider(Protocol):
    provider_code: str

    def create_subscription_checkout(
        self,
        tenant_id: int,
        plan_code: str,
        return_url: str,
        idempotency_key: str,
    ) -> dict[str, Any]: ...

    def cancel_subscription(self, provider_subscription_id: str) -> dict[str, Any]: ...
    def verify_webhook(self, payload: bytes, headers: dict[str, str]) -> dict[str, Any]: ...


def configured_provider(config_key: str):
    """Return a server-configured adapter; credentials stay outside the POS DB/UI."""
    provider = current_app.config.get(config_key)
    if provider is None:
        raise IntegrationNotConfigured(f"{config_key} is not configured")
    return provider() if isinstance(provider, type) else provider
