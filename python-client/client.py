import argparse
import importlib
import sys
import threading
import time
from pathlib import Path
from typing import Any

import grpc


GENERATED_DIR = Path(__file__).resolve().parent / "generated"
if str(GENERATED_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATED_DIR))

try:
    demo_pb2 = importlib.import_module("demo_pb2")
    demo_pb2_grpc = importlib.import_module("demo_pb2_grpc")
except ModuleNotFoundError:
    print("Hianyzik a generalt stub. Futtasd: python python-client/generate_stubs.py")
    raise


def create_channel(target: str) -> grpc.Channel:
    options = [
        ("grpc.enable_retries", 1),
        ("grpc.initial_reconnect_backoff_ms", 500),
        ("grpc.max_reconnect_backoff_ms", 5000),
        ("grpc.keepalive_time_ms", 10000),
        ("grpc.keepalive_timeout_ms", 3000),
        ("grpc.keepalive_permit_without_calls", 1),
    ]

    channel = grpc.insecure_channel(target, options=options)

    def on_state_change(connectivity: grpc.ChannelConnectivity) -> None:
        print(f"[channel] allapot: {connectivity.name}")

    channel.subscribe(on_state_change, try_to_connect=True)
    return channel


def send_ping(stub: Any, client_id: str) -> None:
    now = int(time.time() * 1000)
    request = demo_pb2.PingRequest(
        client_id=client_id,
        sent_unix_ms=now,
        payload="python-client-ping",
    )
    try:
        response = stub.Ping(request, timeout=2.0, wait_for_ready=True)
        rtt = int(time.time() * 1000) - now
        print(
            f"[ping] szerver={response.server_id} rtt={rtt}ms msg='{response.message}'"
        )
    except grpc.RpcError as err:
        print(f"[ping] sikertelen: code={err.code().name} details={err.details()}")


def chat_request_iterator(
    client_id: str, interval_ms: int, stop_event: threading.Event
):
    sequence = 0
    interval_seconds = max(interval_ms, 300) / 1000.0

    while not stop_event.is_set():
        sequence += 1
        now = int(time.time() * 1000)
        text = f"python-uzenet-{sequence}"
        print(f"[send] seq={sequence} text='{text}'")
        yield demo_pb2.ChatMessage(
            from_id=client_id,
            sequence=sequence,
            sent_unix_ms=now,
            text=text,
            kind="CLIENT_EVENT",
        )

        if stop_event.wait(interval_seconds):
            break


def run_bidirectional_stream(
    stub: Any, client_id: str, interval_ms: int
) -> None:
    stop_event = threading.Event()
    response_stream = stub.ChatStream(
        chat_request_iterator(client_id, interval_ms, stop_event),
        wait_for_ready=True,
    )

    try:
        for message in response_stream:
            now_ms = int(time.time() * 1000)
            one_way_delay = now_ms - message.sent_unix_ms
            ack_suffix = f" ack={message.ack_sequence}" if message.ack_sequence else ""
            print(
                f"[recv] kind={message.kind} from={message.from_id} seq={message.sequence}{ack_suffix} "
                f"keses~{one_way_delay}ms text='{message.text}'"
            )

            if message.kind == "ACK" and message.ack_sequence and message.ack_sequence % 5 == 0:
                send_ping(stub, client_id)
    finally:
        stop_event.set()


def run_client(target: str, client_id: str, interval_ms: int) -> None:
    backoff_seconds = 1.0
    attempt = 0

    while True:
        attempt += 1
        channel = create_channel(target)
        stub = demo_pb2_grpc.DemoServiceStub(channel)

        try:
            print(f"\nKapcsolodasi kiserlet #{attempt} cel={target}")
            grpc.channel_ready_future(channel).result(timeout=6)
            print("Kapcsolat letrejott. Bidirectional stream indul...")
            backoff_seconds = 1.0

            run_bidirectional_stream(stub, client_id, interval_ms)
            print("[info] A bidi stream normalisan veget ert.")

        except grpc.FutureTimeoutError:
            print("[hiba] A csatorna nem lett kesz idoben.")
        except grpc.RpcError as err:
            print(f"[hiba] Stream megszakadt: code={err.code().name} details={err.details()}")
        except KeyboardInterrupt:
            print("Leallitas kerve.")
            channel.close()
            return
        finally:
            channel.close()

        print(f"Ujrakapcsolodas {backoff_seconds:.1f} masodperc mulva...")
        time.sleep(backoff_seconds)
        backoff_seconds = min(backoff_seconds * 2, 8.0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Python gRPC kliens demo (Node.js szerverhez)"
    )
    parser.add_argument("--target", default="localhost:50051", help="gRPC szerver cime")
    parser.add_argument("--client-id", default="python-demo-client", help="Kliens azonosito")
    parser.add_argument(
        "--interval-ms",
        type=int,
        default=1000,
        help="A kliens kuldesi intervalluma ms-ban",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_client(args.target, args.client_id, args.interval_ms)
