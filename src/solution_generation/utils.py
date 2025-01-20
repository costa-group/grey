def to_hex_default(value: str):
    """
    Returns the hexadecimal value of the decimal value "value", which is a string. If the conversion is
    not possible, returns directly value
    """
    try:
        return hex(int(value))[2:]
    except:
        return value
