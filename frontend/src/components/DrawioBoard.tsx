"use client";

import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
} from "react";
import { Box, Button, Group } from "@mantine/core";

export type DrawioBoardHandle = {
  submit: () => void;
  exportXml: () => Promise<string>;
  loadXml: (xml: string) => void;
};

type DrawioBoardProps = {
  // The PNG export reply carries the diagram source too, so the XML arrives
  // with the image and needs no second round-trip (verified against
  // embed.diagrams.net). Undefined only if draw.io omits it.
  onExport?: (imageFile: File, xml?: string) => void | Promise<void>;
  onExportError?: (message: string) => void;
  submitting?: boolean;
  hideInternalSubmit?: boolean;
  onAutosave?: (xml: string) => void;
  onSaveRequest?: (xml: string) => void;
  onExitRequest?: () => void;
  initialXml?: string;
};

const DRAWIO_URL = process.env.NEXT_PUBLIC_DRAWIO_ORIGIN?.trim() ?? "https://embed.diagrams.net/?embed=1&spin=1&ui=min&libs=er;general&proto=json";

const DRAWIO_ORIGIN = (() => {
  if (!DRAWIO_URL) return "";
  try {
    return new URL(DRAWIO_URL).origin;
  } catch {
    return DRAWIO_URL;
  }
})();

// Long enough for a slow cross-origin round-trip, short enough that a student
// clicking Submit is never left waiting on a reply that is not coming.
const XML_EXPORT_TIMEOUT_MS = 4000;

type DrawioMessage = {
  event?: "init" | "export" | "autosave" | "save" | "exit";
  data?: string;
  xml?: string;
  format?: "png" | "xml" | "svg";
};

const isDrawioMessage = (value: unknown): value is DrawioMessage => {
  if (typeof value !== "object" || value === null) return false;
  if (!("event" in value)) return false;
  const event = (value as { event?: string }).event;
  return (
    event === "init" ||
    event === "export" ||
    event === "autosave" ||
    event === "save" ||
    event === "exit"
  );
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

export const DrawioBoard = forwardRef<DrawioBoardHandle, DrawioBoardProps>(function DrawioBoard(
  {
    onExport,
    onExportError,
    submitting = false,
    hideInternalSubmit = false,
    onAutosave,
    onSaveRequest,
    onExitRequest,
    initialXml,
  },
  ref,
) {
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const retryTimerRef = useRef<number | null>(null);
  const retryCountRef = useRef(0);
  const initialXmlRef = useRef<string>(initialXml ?? "");
  const xmlExportResolverRef = useRef<((xml: string) => void) | null>(null);
  const xmlExportRejecterRef = useRef<((err: Error) => void) | null>(null);
  const onAutosaveRef = useRef(onAutosave);
  const onSaveRequestRef = useRef(onSaveRequest);
  const onExitRequestRef = useRef(onExitRequest);
  const onExportRef = useRef(onExport);
  const onExportErrorRef = useRef(onExportError);

  useEffect(() => {
    initialXmlRef.current = initialXml ?? initialXmlRef.current;
  }, [initialXml]);

  useEffect(() => {
    onAutosaveRef.current = onAutosave;
  }, [onAutosave]);

  useEffect(() => {
    onSaveRequestRef.current = onSaveRequest;
  }, [onSaveRequest]);

  useEffect(() => {
    onExitRequestRef.current = onExitRequest;
  }, [onExitRequest]);

  useEffect(() => {
    onExportRef.current = onExport;
  }, [onExport]);

  useEffect(() => {
    onExportErrorRef.current = onExportError;
  }, [onExportError]);

  const postToIframe = (message: Record<string, unknown>) => {
    iframeRef.current?.contentWindow?.postMessage(JSON.stringify(message), "*");
  };

  // `autosave: 1` is what makes the editor emit `autosave` events on every
  // change. It belongs on the load message — it is not a URL parameter — and
  // without it onAutosave never fires and no draft is ever captured.
  const sendLoad = () => {
    postToIframe({ action: "load", autosave: 1, xml: initialXmlRef.current });
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

  useImperativeHandle(
    ref,
    () => ({
      submit: () => {
        postToIframe({
          action: "export",
          format: "png",
          bg: "#ffffff",
          transparent: false,
        });
      },
      exportXml: () =>
        new Promise<string>((resolve, reject) => {
          if (xmlExportResolverRef.current) {
            xmlExportRejecterRef.current?.(new Error("Previous XML export superseded."));
          }
          xmlExportResolverRef.current = resolve;
          xmlExportRejecterRef.current = reject;
          postToIframe({ action: "export", format: "xml" });
          // Never let a missing reply wedge a submission: the caller treats a
          // rejection as "no XML" and still submits on the image alone.
          window.setTimeout(() => {
            if (xmlExportResolverRef.current !== resolve) return;
            xmlExportResolverRef.current = null;
            xmlExportRejecterRef.current = null;
            reject(new Error("draw.io did not return the diagram XML in time."));
          }, XML_EXPORT_TIMEOUT_MS);
        }),
      loadXml: (xml: string) => {
        initialXmlRef.current = xml;
        postToIframe({ action: "load", autosave: 1, xml });
      },
    }),
    [],
  );

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
        return;
      }

      if (data.event === "autosave") {
        const xml = data.xml ?? data.data ?? "";
        if (xml) {
          onAutosaveRef.current?.(xml);
        }
        return;
      }

      if (data.event === "save") {
        const xml = data.xml ?? data.data ?? "";
        if (xml) {
          onSaveRequestRef.current?.(xml);
        }
        postToIframe({ action: "status", modified: false });
        return;
      }

      if (data.event === "exit") {
        onExitRequestRef.current?.();
        return;
      }

      if (data.event === "export") {
        if (data.format === "xml") {
          // draw.io puts the XML in `xml` and omits `data` entirely (verified
          // against embed.diagrams.net). `||` not `??`, so an empty `data`
          // string can never win over a populated `xml`.
          const xml = data.xml || data.data || "";
          const resolver = xmlExportResolverRef.current;
          xmlExportResolverRef.current = null;
          xmlExportRejecterRef.current = null;
          resolver?.(xml);
          return;
        }

        void (async () => {
          try {
            const imageFile = await toPngFile(data.data ?? "");
            await onExportRef.current?.(imageFile, data.xml || undefined);
          } catch (err) {
            const message = err instanceof Error ? err.message : "Failed to export PNG from draw.io.";
            onExportErrorRef.current?.(message);
          }
        })();
      }
    };

    window.addEventListener("message", handleMessage);
    return () => {
      window.removeEventListener("message", handleMessage);
      stopRetry();
    };
  }, []);

  const handleExport = () => {
    postToIframe({
      action: "export",
      format: "png",
      bg: "#ffffff",
      transparent: false,
    });
  };

  return (
    <Box
      style={{
        height: "100%",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <Box
        style={{
          flex: 1,
          minHeight: 0,
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
      {hideInternalSubmit ? null : (
        <Group justify="flex-end">
          <Button size="xs" mt="xs" onClick={handleExport} loading={submitting}>
            Submit Diagram
          </Button>
        </Group>
      )}
    </Box>
  );
});
