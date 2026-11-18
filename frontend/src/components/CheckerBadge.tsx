import { useEffect, useState } from "react";

/** vite-plugin-checker 运行时的诊断结构，只在 dev 模式下存在 */
type Diagnostic = {
    message?: string;
    id?: string;
    level?: number;
    loc?: { file?: string; line?: number; column?: number };
};

type CheckerResult = {
    checkerId?: string;
    diagnostics?: Diagnostic[];
};

const HOT_EVENT = "vite-plugin-checker";

/** error 事件给单个对象，reconnect 事件给 [{ event, data }]，统一解包 */
const toResults = (raw: unknown): CheckerResult[] => {
    const list = Array.isArray(raw) ? raw : raw ? [raw] : [];
    return list
        .map((entry) => {
            if (entry && typeof entry === "object" && "data" in entry) {
                return (entry as { data: CheckerResult }).data;
            }
            return entry as CheckerResult;
        })
        .filter((entry): entry is CheckerResult => Boolean(entry && typeof entry === "object"));
};

const shortFile = (file?: string) => {
    if (!file) return "";
    const normalized = file.replace(/\\/g, "/");
    const index = normalized.indexOf("/src/");
    return index >= 0 ? normalized.slice(index + 1) : normalized;
};

const CheckerBadge = () => {
    const [results, setResults] = useState<CheckerResult[]>([]);
    const [open, setOpen] = useState(false);

    useEffect(() => {
        const hot = import.meta.hot;
        if (!hot) return;
        const handle = (payload: { event?: string; data?: unknown }) => {
            if (!payload) return;
            if (payload.event !== `${HOT_EVENT}:error` && payload.event !== `${HOT_EVENT}:reconnect`) {
                return;
            }
            const next = toResults(payload.data);
            setResults((current) => {
                const map = new Map(current.map((item) => [item.checkerId ?? "", item]));
                next.forEach((item) => map.set(item.checkerId ?? "", item));
                return [...map.values()];
            });
        };
        hot.on(HOT_EVENT, handle);
        hot.send(HOT_EVENT, { event: "runtime-loaded" });
        return () => hot.off(HOT_EVENT, handle);
    }, []);

    if (!import.meta.env.DEV) return null;

    const diagnostics = results.flatMap((item) => item.diagnostics ?? []);
    const errors = diagnostics.filter((item) => item.level === 1);
    const warnings = diagnostics.filter((item) => item.level === 0);
    const tone = errors.length ? "#dc2626" : warnings.length ? "#d97706" : "#059669";
    const summary = errors.length
        ? `${errors.length} error${errors.length > 1 ? "s" : ""}`
        : warnings.length
          ? `${warnings.length} warning${warnings.length > 1 ? "s" : ""}`
          : "0 errors";
    const sorted = [...errors, ...warnings];

    return (
        <div
            style={{
                position: "fixed",
                left: 12,
                bottom: 12,
                zIndex: 40,
                fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
            }}
        >
            {open && (
                <div
                    style={{
                        position: "absolute",
                        bottom: "calc(100% + 8px)",
                        left: 0,
                        width: 460,
                        maxWidth: "calc(100vw - 24px)",
                        maxHeight: "40vh",
                        overflow: "auto",
                        padding: "10px 12px",
                        border: "1px solid rgba(148, 163, 184, 0.35)",
                        borderRadius: 10,
                        background: "#ffffff",
                        boxShadow: "0 12px 32px rgba(15, 23, 42, 0.16)",
                        color: "#1f2937",
                        fontSize: 12,
                        lineHeight: 1.6,
                    }}
                >
                    <div
                        style={{
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "space-between",
                            marginBottom: 6,
                            color: "#475569",
                            fontWeight: 600,
                        }}
                    >
                        <span>TypeScript</span>
                        <span style={{ color: tone }}>{summary}</span>
                    </div>
                    {sorted.length === 0 ? (
                        <div style={{ color: "#64748b" }}>没有类型错误</div>
                    ) : (
                        sorted.map((item, index) => {
                            const file = shortFile(item.loc?.file ?? item.id);
                            const position = item.loc?.line
                                ? `${file}:${item.loc.line}${item.loc.column ? `:${item.loc.column}` : ""}`
                                : file;
                            return (
                                <div
                                    key={`${position}-${index}`}
                                    style={{
                                        padding: "6px 0",
                                        borderTop: index === 0 ? "none" : "1px solid rgba(148, 163, 184, 0.2)",
                                    }}
                                >
                                    <div style={{ color: item.level === 1 ? "#dc2626" : "#b45309" }}>
                                        {item.message || "未知错误"}
                                    </div>
                                    {position && (
                                        <div style={{ color: "#64748b", fontSize: 11 }}>{position}</div>
                                    )}
                                </div>
                            );
                        })
                    )}
                </div>
            )}
            <button
                type="button"
                onClick={() => setOpen((value) => !value)}
                title="TypeScript 诊断"
                style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 6,
                    padding: "4px 9px",
                    border: `1px solid ${tone}33`,
                    borderRadius: 6,
                    background: "#ffffff",
                    boxShadow: "0 4px 12px rgba(15, 23, 42, 0.08)",
                    color: "#334155",
                    fontSize: 11,
                    fontWeight: 600,
                    cursor: "pointer",
                }}
            >
                <span
                    style={{
                        width: 6,
                        height: 6,
                        borderRadius: "50%",
                        background: tone,
                        display: "inline-block",
                    }}
                />
                <span>TS</span>
                <span style={{ color: tone }}>{summary}</span>
            </button>
        </div>
    );
};

export default CheckerBadge;
