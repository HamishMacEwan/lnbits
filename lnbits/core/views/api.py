from quart import g, jsonify, request
from http import HTTPStatus
from binascii import unhexlify

from lnbits import bolt11
from lnbits.core import core_app
from lnbits.core.services import create_invoice, pay_invoice
from lnbits.core.crud import delete_expired_invoices
from lnbits.decorators import api_check_wallet_key, api_validate_post_request


@core_app.route("/api/v1/wallet", methods=["GET"])
@api_check_wallet_key("invoice")
async def api_wallet():
    return (
        jsonify(
            {
                "id": g.wallet.id,
                "name": g.wallet.name,
                "balance": g.wallet.balance_msat,
            }
        ),
        HTTPStatus.OK,
    )


@core_app.route("/api/v1/payments", methods=["GET"])
@api_check_wallet_key("invoice")
async def api_payments():
    if "check_pending" in request.args:
        delete_expired_invoices()

        for payment in g.wallet.get_payments(complete=False, pending=True, exclude_uncheckable=True):
            payment.check_pending()

    return jsonify(g.wallet.get_payments(pending=True)), HTTPStatus.OK


@api_check_wallet_key("invoice")
@api_validate_post_request(
    schema={
        "amount": {"type": "integer", "min": 1, "required": True},
        "memo": {"type": "string", "empty": False, "required": True, "excludes": "description_hash"},
        "description_hash": {"type": "string", "empty": False, "required": True, "excludes": "memo"},
    }
)
async def api_payments_create_invoice():
    if "description_hash" in g.data:
        description_hash = unhexlify(g.data["description_hash"])
        memo = ""
    else:
        description_hash = b""
        memo = g.data["memo"]

    try:
        payment_hash, payment_request = create_invoice(
            wallet_id=g.wallet.id, amount=g.data["amount"], memo=memo, description_hash=description_hash
        )
    except Exception as e:
        g.db.rollback()
        return jsonify({"message": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR

    invoice = bolt11.decode(payment_request)
    return (
        jsonify(
            {
                "payment_hash": invoice.payment_hash,
                "payment_request": payment_request,
                # maintain backwards compatibility with API clients:
                "checking_id": invoice.payment_hash,
            }
        ),
        HTTPStatus.CREATED,
    )


@api_check_wallet_key("admin")
@api_validate_post_request(schema={"bolt11": {"type": "string", "empty": False, "required": True}})
async def api_payments_pay_invoice():
    try:
        payment_hash = pay_invoice(wallet_id=g.wallet.id, payment_request=g.data["bolt11"])
    except ValueError as e:
        return jsonify({"message": str(e)}), HTTPStatus.BAD_REQUEST
    except PermissionError as e:
        return jsonify({"message": str(e)}), HTTPStatus.FORBIDDEN
    except Exception as e:
        print(e)
        g.db.rollback()
        return jsonify({"message": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR

    return (
        jsonify(
            {
                "payment_hash": payment_hash,
                # maintain backwards compatibility with API clients:
                "checking_id": payment_hash,
            }
        ),
        HTTPStatus.CREATED,
    )


@core_app.route("/api/v1/payments", methods=["POST"])
@api_validate_post_request(schema={"out": {"type": "boolean", "required": True}})
async def api_payments_create():
    if g.data["out"] is True:
        return await api_payments_pay_invoice()
    return await api_payments_create_invoice()


@core_app.route("/api/v1/payments/<payment_hash>", methods=["GET"])
@api_check_wallet_key("invoice")
async def api_payment(payment_hash):
    payment = g.wallet.get_payment(payment_hash)

    if not payment:
        return jsonify({"message": "Payment does not exist."}), HTTPStatus.NOT_FOUND
    elif not payment.pending:
        return jsonify({"paid": True}), HTTPStatus.OK

    try:
        payment.check_pending()
    except Exception:
        return jsonify({"paid": False}), HTTPStatus.OK

    return jsonify({"paid": not payment.pending}), HTTPStatus.OK
