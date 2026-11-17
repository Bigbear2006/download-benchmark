import argparse
import asyncio
import sys
import time
from dataclasses import dataclass

import aiohttp

DEFAULT_REQUESTS = 10
CHUNK_SIZE = 64 * 1024
MB = 1_000_000  # 1 Мегабайт


@dataclass
class FetchResult:
    size: int  # скачано байт
    elapsed: float  # затрачено секунд

    @property
    def speed(self) -> float:
        return self.size / self.elapsed / MB

    def __repr__(self) -> str:
        return (
            f"{self.size / MB:8.2f} МБ за {self.elapsed:7.3f} с "
            f"({self.speed:7.2f} МБ/с)"
        )


async def fetch(session: aiohttp.ClientSession, url: str) -> FetchResult:
    start = time.perf_counter()
    size = 0
    async with session.get(url) as response:
        response.raise_for_status()
        async for chunk in response.content.iter_chunked(CHUNK_SIZE):
            size += len(chunk)
    elapsed = time.perf_counter() - start
    return FetchResult(size, elapsed)


def get_error_message(exc: Exception) -> str:
    if isinstance(exc, aiohttp.ClientResponseError):
        return f"HTTP {exc.status} {exc.message}"
    if isinstance(exc, asyncio.TimeoutError):
        return "таймаут"
    return f"{type(exc).__name__}: {exc}"


async def run(url: str, count: int) -> int:
    timeout = aiohttp.ClientTimeout(total=None, sock_connect=10, sock_read=30)
    headers = {"Accept-Encoding": "identity"}

    durations: list[float] = []
    total_bytes = 0
    failed = 0

    print(f"URL: {url}")
    print(f"Запросов: {count} (последовательно)\n")

    async with aiohttp.ClientSession(
        timeout=timeout, headers=headers
    ) as session:
        for i in range(1, count + 1):
            try:
                result = await fetch(session, url)
            except (TimeoutError, aiohttp.ClientError) as exc:
                failed += 1
                print(f"[{i:>2}/{count}] ошибка: {get_error_message(exc)}")
                continue

            durations.append(result.elapsed)
            total_bytes += result.size
            print(f"[{i:>2}/{count}] {result}")

    print()
    if not durations:
        print("\nНи один запрос не завершился успешно.")
        return 1

    total_time = sum(durations)
    avg_time = total_time / len(durations)
    speed = total_bytes / total_time / MB

    print(f"Успешных запросов:    {len(durations)} из {count}")
    if failed:
        print(f"Неудачных запросов:   {failed}")
    print(f"Среднее время запроса: {avg_time:.3f} с")
    print(f"Скачано всего:         {total_bytes / MB:.2f} МБ")
    print(f"Скорость скачивания:   {speed:.2f} МБ/с")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Замер скорости скачивания по URL."
    )
    parser.add_argument(
        "url", help="адрес, к которому стучаться (http:// или https://)"
    )
    parser.add_argument(
        "-n",
        "--requests",
        type=int,
        default=DEFAULT_REQUESTS,
        help=f"количество запросов (по умолчанию {DEFAULT_REQUESTS})",
    )
    args = parser.parse_args()

    if not args.url.startswith(("http://", "https://")):
        parser.error("URL должен начинаться с http:// или https://")
    if args.requests < 1:
        parser.error("количество запросов должно быть не меньше 1")
    return args


def main() -> None:
    args = parse_args()
    try:
        sys.exit(asyncio.run(run(args.url, args.requests)))
    except KeyboardInterrupt:
        print("\nПрервано пользователем.")
        sys.exit(130)


if __name__ == "__main__":
    main()
