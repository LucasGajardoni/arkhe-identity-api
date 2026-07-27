from app.services.cpf import validate_cpf


def test_valid_cpf():
    result = validate_cpf("529.982.247-25")
    assert result.formato_valido is True
    assert result.digitos_verificadores_validos is True


def test_invalid_cpf():
    result = validate_cpf("111.111.111-11")
    assert result.formato_valido is True
    assert result.digitos_verificadores_validos is False
