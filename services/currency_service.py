from decimal import Decimal, ROUND_HALF_UP


def to_base(amount, currency, rates):
    #Convert `amount` in `currency` to the base currency (EUR).
    rate = Decimal(str(rates[currency]))
    return (Decimal(str(amount)) * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)