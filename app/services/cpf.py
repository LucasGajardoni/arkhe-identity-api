from dataclasses import dataclass


@dataclass(frozen=True)
class CPFValidation:
    digits: str
    formato_valido: bool
    digitos_verificadores_validos: bool


def only_digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def validate_cpf(value: str) -> CPFValidation:
    digits = only_digits(value)
    format_ok = len(digits) == 11
    if not format_ok or digits == digits[:1] * 11:
        return CPFValidation(digits=digits, formato_valido=format_ok, digitos_verificadores_validos=False)

    def digit_for(prefix: str, start_weight: int) -> str:
        total = sum(int(num) * weight for num, weight in zip(prefix, range(start_weight, 1, -1), strict=True))
        remainder = (total * 10) % 11
        return "0" if remainder == 10 else str(remainder)

    first = digit_for(digits[:9], 10)
    second = digit_for(digits[:10], 11)
    return CPFValidation(
        digits=digits,
        formato_valido=True,
        digitos_verificadores_validos=digits[-2:] == first + second,
    )
