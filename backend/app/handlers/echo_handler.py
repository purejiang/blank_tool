def echo(*args):
    return {"received_params": args}

API_MAP = {
    "echo": echo,
}