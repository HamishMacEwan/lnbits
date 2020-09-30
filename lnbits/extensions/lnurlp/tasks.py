import httpx

from lnbits.core.models import Payment

from .crud import get_pay_link_by_invoice, mark_webhook_sent


async def on_invoice_paid(payment: Payment) -> None:
    islnurlp = "lnurlp" == payment.extra.get("tag")
    if islnurlp:
        pay_link = get_pay_link_by_invoice(payment.payment_hash)
        if not pay_link:
            # no pay_link or this webhook has already been sent
            return
        if pay_link.webhook_url:
            async with httpx.AsyncClient() as client:
                try:
                    r = await client.post(
                        pay_link.webhook_url,
                        json={
                            "payment_hash": payment.payment_hash,
                            "payment_request": payment.bolt11,
                            "amount": payment.amount,
                            "lnurlp": pay_link.id,
                        },
                        timeout=40,
                    )
                    mark_webhook_sent(payment.payment_hash, r.status_code)
                except httpx.RequestError:
                    mark_webhook_sent(payment.payment_hash, -1)
