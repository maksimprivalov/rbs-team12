"""Benigni CPU primer - izračuna proste brojeve do N (pokazuje da kod stvarno radi)."""


def primes_up_to(n: int) -> list[int]:
    sieve = [True] * (n + 1)
    sieve[0:2] = [False, False]
    for i in range(2, int(n**0.5) + 1):
        if sieve[i]:
            for j in range(i * i, n + 1, i):
                sieve[j] = False
    return [i for i, is_p in enumerate(sieve) if is_p]


if __name__ == "__main__":
    primes = primes_up_to(10_000)
    print(f"Prostih brojeva do 10000: {len(primes)}")
    print(f"Poslednjih 5: {primes[-5:]}")
