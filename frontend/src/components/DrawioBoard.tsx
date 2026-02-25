"use client";

import { useEffect, useRef } from "react";
import { Box, Button, Group } from "@mantine/core";

type DrawioBoardProps = {
  onExport?: (xml: string) => void | Promise<void>;
  submitting?: boolean;
};

const DRAWIO_ORIGIN = "http://localhost:8080";

type DrawioMessage = {
  event?: "init" | "export";
  data?: string;
};

const isDrawioMessage = (value: unknown): value is DrawioMessage => {
  if (typeof value !== "object" || value === null) return false;
  if (!("event" in value)) return false;
  const event = (value as { event?: string }).event;
  return event === "init" || event === "export";
};

export function DrawioBoard({ onExport, submitting = false }: DrawioBoardProps) {
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const retryTimerRef = useRef<number | null>(null);
  const retryCountRef = useRef(0);

  const sendLoad = () => {
    iframeRef.current?.contentWindow?.postMessage(
      JSON.stringify({ action: "load", xml: "" }),
      "*"
    );
  };

  const stopRetry = () => {
    if (retryTimerRef.current !== null) {
      window.clearInterval(retryTimerRef.current);
      retryTimerRef.current = null;
    }
  };

  const startRetry = () => {
    if (retryTimerRef.current !== null) return;
    retryCountRef.current = 0;
    retryTimerRef.current = window.setInterval(() => {
      retryCountRef.current += 1;
      sendLoad();
      if (retryCountRef.current >= 8) {
        stopRetry();
      }
    }, 250);
  };

  useEffect(() => {
    console.log("hello");
    const handleMessage = (event: MessageEvent) => {
      console.log("msg:", event.origin, event.data);
      if (event.origin !== DRAWIO_ORIGIN) return;
      const iframeWindow = iframeRef.current?.contentWindow;
      if (iframeWindow && event.source !== iframeWindow) return;

      let data: DrawioMessage | null = null;
      if (typeof event.data === "string") {
        try {
          data = JSON.parse(event.data);
        } catch {
          return;
        }
      } else if (typeof event.data === "object" && event.data !== null) {
        data = event.data as DrawioMessage;
      } else {
        return;
      }

      if (!data || !isDrawioMessage(data)) return;

      if (data.event === "init") {
        stopRetry();
        sendLoad();
      }

      if (data.event === "export") {
        const diagramXml = data.data ?? "";
        onExport?.(diagramXml);
      }
    };

    window.addEventListener("message", handleMessage);
    return () => {
      window.removeEventListener("message", handleMessage);
      stopRetry();
    };
  }, [onExport]);

  const handleExport = () => {
    iframeRef.current?.contentWindow?.postMessage(
      JSON.stringify({ action: "export", format: "xmlsvg" }),
      "*"
    );
  };

  return (
    <Box>
      <Box
        style={{
          height: "60vh",
          border: "1px solid var(--mantine-color-gray-3)",
          borderRadius: 12,
          overflow: "hidden",
        }}
      >
        <iframe
          ref={iframeRef}
          title="Draw.io"
          src="http://localhost:8080/?embed=1&spin=1&ui=min&libs=er&proto=json"
          onLoad={() => {
            console.log("iframe loaded");
            sendLoad();
            startRetry();
          }}
          style={{ width: "100%", height: "100%", border: "none" }}
        />
      </Box>
      <Group justify="flex-end">
        <Button size="xs" mt="xs" onClick={handleExport} loading={submitting}>
          Submit Diagram
        </Button>
      </Group>
    </Box>
  );
}
