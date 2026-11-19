import { useCallback, useEffect, useMemo, useState } from "react";
import "@/styles/wiki-content.css";

type Detail = "sources" | "lint" | "reviews";

type SourceItem = {
    name: string;
    path: string;
    size: number;
    ext: string;
    modifiedAt: string;
    ingested: boolean;
    wikiPage: string;
    wikiPages: number;
};

type ReviewOption = { label?: string; action?: string };

type ReviewItem = {
    id: string;
    type?: string;
    title?: string;
    description?: string;
    sourcePath?: string;
    affectedPages?: string[];
    searchQueries?: string[];
    options?: ReviewOption[];
};

type LintIssue = {
    level: string;
    code: string;
    file: string;
    message: string;
};

type LintData = {
    issues: LintIssue[];
    stats: { pages: number; errors: number; warnings: number };
};

type ProjectItem = { id: string; name: string; exists: boolean };

const CODE_LABELS: Record<string, string> = {
    "missing-frontmatter": "frontmatter 缺失",
    "missing-title": "标题缺失",
    "missing-type": "类型缺失",
    "missing-source": "来源缺失",
    "broken-wikilink": "断链",
    "orphan-page": "孤立页面",
    "not-in-index": "索引未收录",
    "empty-page": "空页面",
};

const GROUP_LIMIT = 10;

const formatSize = (size: number) => {
    if (size >= 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`;
    if (size >= 1024) return `${Math.round(size / 1024)} KB`;
    return `${size} B`;
};

const formatTime = (iso: string) => {
    if (!iso) return "";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "";
    return `${date.getMonth() + 1}月${date.getDate()}日 ${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
};

const shortPath = (path: string) => {
    const normalized = path.replace(/\\/g, "/");
    const index = normalized.indexOf("wiki/");
    return index >= 0 ? normalized.slice(index) : normalized;
};

const WikiContentPanel = ({ projectId }: { projectId?: string }) => {
    const [project, setProject] = useState<ProjectItem | null>(null);
    const [sources, setSources] = useState<SourceItem[]>([]);
    const [reviews, setReviews] = useState<ReviewItem[]>([]);
    const [lint, setLint] = useState<LintData>({ issues: [], stats: { pages: 0, errors: 0, warnings: 0 } });
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [busyId, setBusyId] = useState("");
    const [detail, setDetail] = useState<Detail | null>(null);
    const [expanded, setExpanded] = useState<Record<string, boolean>>({});

    const load = useCallback(async () => {
        setLoading(true);
        setError("");
        setSources([]);
        setReviews([]);
        setLint({ issues: [], stats: { pages: 0, errors: 0, warnings: 0 } });
        setDetail(null);
        setProject(null);
        const currentId = projectId || "default";
        try {
            const [projectResponse, documentResponse] = await Promise.all([
                fetch("/api/wiki/projects").catch(() => null),
                fetch(`/api/documents?project_id=${encodeURIComponent(currentId)}`),
            ]);
            const projectData = projectResponse?.ok
                ? ((await projectResponse.json()) as { items: ProjectItem[] })
                : { items: [] as ProjectItem[] };
            const wikiProjects = projectData.items || [];
            const current = wikiProjects.find(
                (item) => item.id === currentId || item.name === currentId,
            ) ?? null;
            if (current) {
                setProject(current);
                const query = `?project=${encodeURIComponent(current.id)}`;
                const [sourceResponse, reviewResponse, lintResponse] = await Promise.all([
                    fetch(`/api/wiki/sources${query}`),
                    fetch(`/api/wiki/reviews${query}`),
                    fetch(`/api/wiki/lint${query}`),
                ]);
                if (!sourceResponse.ok || !reviewResponse.ok || !lintResponse.ok) {
                    throw new Error("LLM Wiki 数据读取失败");
                }
                const sourceData = (await sourceResponse.json()) as { items: SourceItem[] };
                const reviewData = (await reviewResponse.json()) as { items: ReviewItem[] };
                const lintData = (await lintResponse.json()) as LintData;
                setSources(sourceData.items || []);
                setReviews(reviewData.items || []);
                setLint({ issues: lintData.issues || [], stats: lintData.stats });
            } else if (documentResponse.ok) {
                const documentData = (await documentResponse.json()) as {
                    items: { id: string; filename: string; size: number; mime: string; createdAt: string; chunks: number; status: string }[];
                };
                const items = documentData.items || [];
                setProject({ id: currentId, name: "当前项目", exists: true });
                setSources(
                    items.map((item) => ({
                        name: item.filename,
                        path: item.id,
                        size: item.size,
                        ext: item.filename.includes(".") ? item.filename.split(".").pop() || "file" : "file",
                        modifiedAt: item.createdAt,
                        ingested: item.chunks > 0,
                        wikiPage: "",
                        wikiPages: 0,
                    })),
                );
                setLint({
                    issues: [],
                    stats: { pages: items.reduce((sum, item) => sum + (item.chunks > 0 ? 1 : 0), 0), errors: 0, warnings: 0 },
                });
            }
        } catch (reason) {
            setError(reason instanceof Error ? reason.message : "加载失败");
        } finally {
            setLoading(false);
        }
    }, [projectId]);

    useEffect(() => {
        void load();
    }, [load]);

    const lintGroups = useMemo(() => {
        const order = ["missing-frontmatter", "missing-source", "empty-page", "broken-wikilink", "orphan-page", "missing-type", "not-in-index"];
        const groups = new Map<string, LintIssue[]>();
        lint.issues.forEach((issue) => {
            const list = groups.get(issue.code) || [];
            list.push(issue);
            groups.set(issue.code, list);
        });
        return [...groups.entries()].sort((a, b) => {
            const rankA = order.indexOf(a[0]);
            const rankB = order.indexOf(b[0]);
            return (rankA < 0 ? 99 : rankA) - (rankB < 0 ? 99 : rankB);
        });
    }, [lint.issues]);

    const resolveReview = async (item: ReviewItem, action: string) => {
        if (!project) return;
        setBusyId(item.id);
        try {
            const response = await fetch(`/api/wiki/reviews/${encodeURIComponent(item.id)}?project=${encodeURIComponent(project.id)}`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ action }),
            });
            if (!response.ok) throw new Error("处理失败");
            setReviews((current) => current.filter((entry) => entry.id !== item.id));
        } catch {
            setError("审核项处理失败，请稍后重试");
        } finally {
            setBusyId("");
        }
    };

    const latestSource = sources[0];
    const latestReview = reviews[0];
    const lintTotal = lint.stats.errors + lint.stats.warnings;

    const renderDetail = () => {
        if (detail === "sources") {
            return sources.length === 0 ? (
                <div className="hc-wiki__empty">还没有原始资料</div>
            ) : (
                <ul className="hc-wiki__list">
                    {sources.map((item) => (
                        <li key={item.path} className="hc-wiki__source">
                            <span className={`hc-wiki__file hc-wiki__file--${item.ext || "file"}`}>{item.ext || "file"}</span>
                            <div className="hc-wiki__source-main">
                                <div className="hc-wiki__source-name" title={item.name}>
                                    {item.name}
                                </div>
                                <div className="hc-wiki__meta">
                                    {formatSize(item.size)} · {formatTime(item.modifiedAt)} ·{" "}
                                    {item.wikiPage ? `${item.wikiPages} 个关联页面` : "尚未生成 Wiki 页面"}
                                </div>
                            </div>
                            <span className={`hc-wiki__badge${item.ingested ? " is-ok" : " is-idle"}`}>
                                {item.ingested ? "已摄入" : "未摄入"}
                            </span>
                        </li>
                    ))}
                </ul>
            );
        }

        if (detail === "lint") {
            return (
                <>
                    <div className="hc-wiki__stats">
                        <span className="hc-wiki__stat is-error">{lint.stats.errors} 错误</span>
                        <span className="hc-wiki__stat is-warn">{lint.stats.warnings} 警告</span>
                        <span className="hc-wiki__stat">{lint.stats.pages} 页面</span>
                    </div>
                    {lintGroups.length === 0 ? (
                        <div className="hc-wiki__empty">检查通过，没有发现问题</div>
                    ) : (
                        lintGroups.map(([code, list]) => {
                            const isOpen = expanded[code] ?? code === "missing-frontmatter";
                            return (
                                <div key={code} className="hc-wiki__group">
                                    <button
                                        type="button"
                                        className="hc-wiki__group-head"
                                        onClick={() => setExpanded((current) => ({ ...current, [code]: !isOpen }))}
                                    >
                                        <span className="hc-wiki__caret">{isOpen ? "▾" : "▸"}</span>
                                        {CODE_LABELS[code] || code}
                                        <span className="hc-wiki__count">{list.length}</span>
                                    </button>
                                    {isOpen ? (
                                        <ul className="hc-wiki__issues">
                                            {list.slice(0, GROUP_LIMIT).map((issue, index) => (
                                                <li key={`${issue.file}-${index}`} className="hc-wiki__issue">
                                                    <span className={`hc-wiki__level is-${issue.level}`}>
                                                        {issue.level === "error" ? "错误" : "警告"}
                                                    </span>
                                                    <div>
                                                        <div className="hc-wiki__issue-text">{issue.message}</div>
                                                        <div className="hc-wiki__meta">{shortPath(issue.file)}</div>
                                                    </div>
                                                </li>
                                            ))}
                                            {list.length > GROUP_LIMIT ? (
                                                <li className="hc-wiki__more">还有 {list.length - GROUP_LIMIT} 条未显示</li>
                                            ) : null}
                                        </ul>
                                    ) : null}
                                </div>
                            );
                        })
                    )}
                </>
            );
        }

        return reviews.length === 0 ? (
            <div className="hc-wiki__empty">没有待审阅项</div>
        ) : (
            <ul className="hc-wiki__list">
                {reviews.map((item) => (
                    <li key={item.id} className="hc-wiki__review">
                        <div className="hc-wiki__review-head">
                            <span className="hc-wiki__tag">{item.type || "suggestion"}</span>
                            <span className="hc-wiki__review-title">{item.title || "未命名审核项"}</span>
                        </div>
                        {item.description ? <p className="hc-wiki__review-desc">{item.description}</p> : null}
                        {item.affectedPages && item.affectedPages.length > 0 ? (
                            <div className="hc-wiki__meta">影响：{item.affectedPages.map(shortPath).join("、")}</div>
                        ) : null}
                        <div className="hc-wiki__actions">
                            {(item.options || []).map((option) => {
                                const action = option.action || option.label || "Skip";
                                return (
                                    <button
                                        key={action}
                                        type="button"
                                        className={`hc-wiki__action${action === "Skip" ? " is-ghost" : ""}`}
                                        disabled={busyId === item.id}
                                        onClick={() => void resolveReview(item, action)}
                                    >
                                        {option.label || action}
                                    </button>
                                );
                            })}
                        </div>
                    </li>
                ))}
            </ul>
        );
    };

    return (
        <section className={`hc-wiki${detail ? " hc-wiki--expanded" : ""}`} aria-label="我的内容">
            <header className="hc-wiki__head">
                <div className="hc-wiki__title">
                    <span className="hc-wiki__dot" aria-hidden="true" />
                    我的内容
                    {project ? <span className="hc-wiki__project">{project.name}</span> : null}
                    {detail ? <span className="hc-wiki__crumb">{detail === "sources" ? "原始资料" : detail === "lint" ? "检查" : "待审阅"}</span> : null}
                </div>
                <div className="hc-wiki__tools">
                    {detail ? (
                        <button type="button" className="hc-wiki__refresh" onClick={() => setDetail(null)}>
                            返回
                        </button>
                    ) : null}
                    <button type="button" className="hc-wiki__refresh" onClick={() => void load()} disabled={loading}>
                        {loading ? "同步中…" : "刷新"}
                    </button>
                </div>
            </header>

            {error ? <div className="hc-wiki__error">{error}</div> : null}

            {!loading && !error && !project ? (
                <div className="hc-wiki__empty">当前项目暂未关联 LLM Wiki 资料</div>
            ) : detail ? (
                <div className="hc-wiki__detail">{renderDetail()}</div>
            ) : (
                <div className="hc-wiki__cards">
                    <button type="button" className="hc-wiki__card hc-wiki__card--violet" onClick={() => setDetail("sources")}>
                        <div className="hc-wiki__card-top">
                            <div>
                                <div className="hc-wiki__card-name">原始资料</div>
                                <div className="hc-wiki__card-kind">SOURCES</div>
                            </div>
                            <span className="hc-wiki__card-glyph">▤</span>
                        </div>
                        <div className="hc-wiki__card-number">{sources.length}</div>
                        <div className="hc-wiki__card-bottom">
                            <span title={latestSource?.name}>
                                {loading
                                    ? "读取中…"
                                    : latestSource
                                      ? `${formatSize(latestSource.size)} · ${latestSource.ingested ? "已摄入" : "未摄入"}`
                                      : "上传后自动入库"}
                            </span>
                            <span className="hc-wiki__card-arrow">→</span>
                        </div>
                    </button>

                    <button type="button" className="hc-wiki__card hc-wiki__card--teal" onClick={() => setDetail("lint")}>
                        <div className="hc-wiki__card-top">
                            <div>
                                <div className="hc-wiki__card-name">检查</div>
                                <div className="hc-wiki__card-kind">LINT</div>
                            </div>
                            <span className="hc-wiki__card-glyph">◎</span>
                        </div>
                        <div className="hc-wiki__card-number">{lintTotal}</div>
                        <div className="hc-wiki__card-bottom">
                            <span>
                                {lint.stats.errors} 错误 · {lint.stats.warnings} 警告 · {lint.stats.pages} 页面
                            </span>
                            <span className="hc-wiki__card-arrow">→</span>
                        </div>
                    </button>

                    <button type="button" className="hc-wiki__card hc-wiki__card--blue" onClick={() => setDetail("reviews")}>
                        <div className="hc-wiki__card-top">
                            <div>
                                <div className="hc-wiki__card-name">待审阅</div>
                                <div className="hc-wiki__card-kind">REVIEW</div>
                            </div>
                            <span className="hc-wiki__card-glyph">◈</span>
                        </div>
                        <div className="hc-wiki__card-number">{reviews.length}</div>
                        <div className="hc-wiki__card-bottom">
                            <span title={latestReview?.title}>
                                {loading
                                    ? "读取中…"
                                    : latestReview
                                      ? latestReview.title || "未命名审核项"
                                      : "队列已清空"}
                            </span>
                            <span className="hc-wiki__card-arrow">→</span>
                        </div>
                    </button>
                </div>
            )}
        </section>
    );
};

export default WikiContentPanel;
