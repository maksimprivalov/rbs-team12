# Benigni test 2: Računanje prostih brojeva (Sieve of Eratosthenes)
# Očekivano: SAFE, status READY

def sieve(n: int) -> list[int]:
    is_prime = [True] * (n + 1)
    is_prime[0] = is_prime[1] = False
    for i in range(2, int(n**0.5) + 1):
        if is_prime[i]:
            for j in range(i * i, n + 1, i):
                is_prime[j] = False
    return [i for i in range(2, n + 1) if is_prime[i]]

primes = sieve(100)
print(f"Prvih {len(primes)} prostih brojeva do 100: {primes}")
