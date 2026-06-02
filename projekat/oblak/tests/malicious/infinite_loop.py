# Maliciozni test 4: Beskonačna petlja (timeout test)
# Očekivano: Prođe analizu (nema HIGH Bandit nalaza), ali Firecracker timeout ubija VM
# LLM može da prepozna kao SUSPICIOUS

while True:
    pass
