import argparse
import asyncio
import sys
import time

import aiohttp

DEFAULT_REQUESTS = 10
CHUNK_SIZE = 64 * 1024  # читаем тело кусками, чтобы не держать файл в памяти
MB = 1_000_000  # 1 МБ = 10^6 байт


async def fetch_once(session: aiohttp.ClientSession, url: str) -> tuple[int, float]:
    """Выполняет один GET и возвращает (скачано_байт, затрачено_секунд).

    Время считается от отправки запроса до получения последнего байта тела.
    """
    start = time.perf_counter()
    size = 0
    async with session.get(url) as response:
        response.raise_for_status()
        async for chunk in response.content.iter_chunked(CHUNK_SIZE):
            size += len(chunk)
    elapsed = time.perf_counter() - start
    return size, elapsed


def describe_error(exc: Exception) -> str:
    """Короткое человекочитаемое описание ошибки запроса."""
    if isinstance(exc, aiohttp.ClientResponseError):
        return f"HTTP {exc.status} {exc.message}"
    if isinstance(exc, asyncio.TimeoutError):
        return "таймаут"
    return f"{type(exc).__name__}: {exc}"


async def run(url: str, count: int) -> int:
    # total=None: тяжёлый файл может качаться долго, общий лимит не ставим,
    # но зависшее соединение (нет данных 30 с) обрываем.
    timeout = aiohttp.ClientTimeout(total=None, sock_connect=10, sock_read=30)
    # Просим сервер не сжимать ответ, чтобы объём был равен реально переданному.
    headers = {"Accept-Encoding": "identity"}

    durations: list[float] = []
    total_bytes = 0
    failed = 0

    print(f"URL: {url}")
    print(f"Запросов: {count} (последовательно)\n")

    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        for i in range(1, count + 1):
            try:
                size, elapsed = await fetch_once(session, url)
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                failed += 1
                print(f"[{i:>2}/{count}] ошибка: {describe_error(exc)}")
                continue

            durations.append(elapsed)
            total_bytes += size
            speed = size / elapsed / MB
            print(
                f"[{i:>2}/{count}] {size / MB:8.2f} МБ за {elapsed:7.3f} с "
                f"({speed:7.2f} МБ/с)"
            )

    print()
    if not durations:
        print("Ни один запрос не завершился успешно.")
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
        description="Замер скорости скачивания по URL (aiohttp)."
    )
    parser.add_argument("url", help="адрес, к которому стучаться (http:// или https://)")
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
