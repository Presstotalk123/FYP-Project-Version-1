"use client";

import { useEffect, useRef } from "react";
import { Box, Button, Group } from "@mantine/core";

type DrawioBoardProps = {
  onExport?: (imageFile: File) => void | Promise<void>;
  onExportError?: (message: string) => void;
  submitting?: boolean;
};

const DRAWIO_URL = process.env.NEXT_PUBLIC_DRAWIO_ORIGIN?.trim() ?? "";

const DRAWIO_ORIGIN = (() => {
  if (!DRAWIO_URL) return "";
  try {
    return new URL(DRAWIO_URL).origin;
  } catch {
    return DRAWIO_URL;
  }
})();

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

const toPngBlob = (rawExportData: string): Blob => {
  const payload = rawExportData.trim();
  if (!payload) {
    throw new Error("Draw.io did not return any PNG data.");
  }

  let base64Payload = payload;
  if (payload.startsWith("data:")) {
    const commaIndex = payload.indexOf(",");
    if (commaIndex < 0) {
      throw new Error("Draw.io returned malformed PNG export data.");
    }

    const metadata = payload.slice(0, commaIndex).toLowerCase();
    if (!metadata.includes("image/png") || !metadata.includes(";base64")) {
      throw new Error("Draw.io export is not a PNG image.");
    }

    base64Payload = payload.slice(commaIndex + 1);
  }

  const normalizedBase64 = base64Payload.replace(/\s+/g, "");
  if (!normalizedBase64) {
    throw new Error("Draw.io returned empty PNG data.");
  }

  let binary = "";
  try {
    binary = window.atob(normalizedBase64);
  } catch {
    throw new Error("Draw.io returned invalid PNG data.");
  }

  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }

  return new Blob([bytes], { type: "image/png" });
};

const toWhiteBackgroundPngFile = (blob: Blob): Promise<File> =>
  new Promise((resolve, reject) => {
    const imageUrl = URL.createObjectURL(blob);
    const image = new Image();

    image.onload = () => {
      try {
        const canvas = document.createElement("canvas");
        canvas.width = image.naturalWidth || image.width;
        canvas.height = image.naturalHeight || image.height;
        const ctx = canvas.getContext("2d");
        if (!ctx || !canvas.width || !canvas.height) {
          reject(new Error("Failed to prepare PNG canvas."));
          return;
        }

        // Force white background before drawing exported PNG.
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(image, 0, 0);

        canvas.toBlob((whiteBlob) => {
          if (!whiteBlob) {
            reject(new Error("Failed to create PNG preview file."));
            return;
          }

          resolve(new File([whiteBlob], "drawio-submission.png", { type: "image/png" }));
        }, "image/png");
      } finally {
        URL.revokeObjectURL(imageUrl);
      }
    };

    image.onerror = () => {
      URL.revokeObjectURL(imageUrl);
      reject(new Error("Failed to decode exported PNG image."));
    };

    image.src = imageUrl;
  });

const toPngFile = async (rawExportData: string): Promise<File> => {
  const pngBlob = toPngBlob(rawExportData);
  return toWhiteBackgroundPngFile(pngBlob);
};

export function DrawioBoard({ onExport, onExportError, submitting = false }: DrawioBoardProps) {
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
    const handleMessage = (event: MessageEvent) => {
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
        void (async () => {
          try {
            const imageFile = await toPngFile(data.data ?? "");
            await onExport?.(imageFile);
          } catch (err) {
            const message = err instanceof Error ? err.message : "Failed to export PNG from draw.io.";
            onExportError?.(message);
          }
        })();
      }
    };

    window.addEventListener("message", handleMessage);
    return () => {
      window.removeEventListener("message", handleMessage);
      stopRetry();
    };
  }, [onExport, onExportError]);

  const handleExport = () => {
    iframeRef.current?.contentWindow?.postMessage(
      JSON.stringify({
        action: "export",
        format: "png",
        bg: "#ffffff",
        transparent: false,
      }),
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
          src={DRAWIO_URL}
          onLoad={() => {
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
