"use strict";

const path = require("path");
const grpc = require("@grpc/grpc-js");
const protoLoader = require("@grpc/proto-loader");

const PROTO_PATH = path.join(__dirname, "..", "proto", "demo.proto");
const SERVER_ID = "node-server-1";
const DEFAULT_PORT = process.env.GRPC_PORT || "50051";
const BIND_ADDRESS = `0.0.0.0:${DEFAULT_PORT}`;

const packageDefinition = protoLoader.loadSync(PROTO_PATH, {
  keepCase: true,
  longs: String,
  enums: String,
  defaults: true,
  oneofs: true
});

const proto = grpc.loadPackageDefinition(packageDefinition).demo.v1;

function ping(call, callback) {
  const now = Date.now();
  const clientId = call.request.client_id || "unknown-client";

  callback(null, {
    server_id: SERVER_ID,
    received_unix_ms: now,
    echoed_client_unix_ms: call.request.sent_unix_ms || 0,
    message: `Hello ${clientId}, gRPC unary hivas rendben.`
  });
}

function subscribeTicks(call) {
  const clientId = call.request.client_id || "unknown-client";
  const requestedInterval = call.request.interval_ms || 1000;
  const intervalMs = Math.min(5000, Math.max(300, requestedInterval));
  const peer = call.getPeer();
  let sequence = 0;
  let timer = null;
  let closed = false;

  console.log(
    `[stream] uj kapcsolat client=${clientId} peer=${peer} interval=${intervalMs}ms`
  );

  const pushTick = () => {
    sequence += 1;
    const now = Date.now();
    call.write({
      sequence,
      server_unix_ms: now,
      server_time_iso: new Date(now).toISOString()
    });
  };

  const closeStream = (reason) => {
    if (closed) {
      return;
    }
    closed = true;
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
    console.log(`[stream] lezarva client=${clientId} reason=${reason}`);
  };

  pushTick();
  timer = setInterval(pushTick, intervalMs);

  call.on("cancelled", () => closeStream("cancelled"));
  call.on("close", () => closeStream("close"));
  call.on("error", (err) => closeStream(`error:${err.message}`));
}

function chatStream(call) {
  const peer = call.getPeer();
  let clientId = "unknown-client";
  let closed = false;
  let serverSequence = 0;
  let heartbeatTimer = null;

  const closeStream = (reason) => {
    if (closed) {
      return;
    }
    closed = true;
    if (heartbeatTimer) {
      clearInterval(heartbeatTimer);
      heartbeatTimer = null;
    }
    console.log(`[bidi] lezarva client=${clientId} peer=${peer} reason=${reason}`);
  };

  const writeServerMessage = (kind, text, ackSequence = 0) => {
    if (closed) {
      return;
    }
    serverSequence += 1;
    call.write({
      from_id: SERVER_ID,
      sequence: serverSequence,
      sent_unix_ms: Date.now(),
      text,
      ack_sequence: ackSequence,
      kind
    });
  };

  writeServerMessage("WELCOME", "Bidi stream letrejott.");

  heartbeatTimer = setInterval(() => {
    writeServerMessage("HEARTBEAT", "Szerver eletjel.");
  }, 3000);

  call.on("data", (message) => {
    clientId = message.from_id || clientId;
    const text = message.text || "";
    const clientSequence = Number(message.sequence || 0);

    console.log(
      `[bidi] bejovo client=${clientId} seq=${clientSequence} text='${text}'`
    );

    writeServerMessage("ACK", `Uzenet fogadva (${text})`, clientSequence);
  });

  call.on("end", () => {
    closeStream("client-end");
    call.end();
  });
  call.on("cancelled", () => closeStream("cancelled"));
  call.on("close", () => closeStream("close"));
  call.on("error", (err) => closeStream(`error:${err.message}`));
}

function main() {
  const server = new grpc.Server();

  server.addService(proto.DemoService.service, {
    Ping: ping,
    SubscribeTicks: subscribeTicks,
    ChatStream: chatStream
  });

  server.bindAsync(
    BIND_ADDRESS,
    grpc.ServerCredentials.createInsecure(),
    (err, port) => {
      if (err) {
        console.error("Nem sikerult a szerver inditasa:", err);
        process.exit(1);
      }

      console.log(`gRPC Node.js szerver fut: ${BIND_ADDRESS} (bindelt port: ${port})`);
      console.log("Allitsd le (Ctrl+C), majd inditsd ujra a reconnect demohoz.");
      server.start();
    }
  );

  const shutdown = () => {
    console.log("Leallitas...");
    server.tryShutdown((shutdownErr) => {
      if (shutdownErr) {
        console.error("Hiba a szerver leallitasakor:", shutdownErr);
        process.exit(1);
      }
      process.exit(0);
    });
  };

  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
}

main();
