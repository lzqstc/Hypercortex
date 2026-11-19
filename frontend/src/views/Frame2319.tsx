import { useState } from "react";
import { useNavigate } from "react-router";
import { api } from "@/services/api";
import { useFeedback } from "@/components/Feedback";
import { navTo, pressable } from "@/utils/nav";
import { getCurrentProject, setCurrentProject } from "@/utils/project";
import ProjectSidebarList from "@/components/ProjectSidebarList";
import QuickSearch from "@/components/QuickSearch";
import "@/styles/Frame2319.css";
const Frame2319 = () => {
    const navigate = useNavigate();
    const { notify, track } = useFeedback();
    const [projectName, setProjectName] = useState("");
    const [template, setTemplate] = useState("产品知识库");
    const [team, setTeam] = useState("产品与体验中心");
    const [visibility, setVisibility] = useState("团队可见 · 34 人");
    const [autoSync, setAutoSync] = useState(true);
    const [deepSearch, setDeepSearch] = useState(true);
    const [citations, setCitations] = useState(false);
    const [searchOpen, setSearchOpen] = useState(false);

    const selectTemplate = (value: string) => {
        setTemplate(value);
        notify(`已选择模板：${value}`);
    };

    const cycleTeam = () => {
        const teams = ["产品与体验中心", "法务合规中心", "供应链运营中心"];
        const next = teams[(teams.indexOf(team) + 1) % teams.length];
        setTeam(next);
        notify(`所属团队已切换为：${next}`);
    };

    const cycleVisibility = () => {
        const options = ["团队可见 · 34 人", "仅自己可见", "获得链接的人可见"];
        const next = options[(options.indexOf(visibility) + 1) % options.length];
        setVisibility(next);
        notify(`可见范围已切换为：${next}`);
    };

    const updateSetting = async (key: "autoSync" | "deepSearch" | "citations") => {
        const next = {
            autoSync: key === "autoSync" ? !autoSync : autoSync,
            deepSearch: key === "deepSearch" ? !deepSearch : deepSearch,
            citations: key === "citations" ? !citations : citations,
        };
        if (key === "autoSync") setAutoSync(next.autoSync);
        if (key === "deepSearch") setDeepSearch(next.deepSearch);
        if (key === "citations") setCitations(next.citations);
        notify(`${key === "autoSync" ? "自动同步" : key === "deepSearch" ? "深度思考" : "引用来源"}已${next[key] ? "开启" : "关闭"}`);
        void track(() => api.settings.update({ [key]: next[key] as boolean }), {
            error: "设置同步失败",
        });
    };

    const applyRecommended = () => {
        setAutoSync(true);
        setDeepSearch(true);
        setCitations(true);
        setTemplate("产品知识库");
        notify("已应用推荐配置：语义切片 · 混合检索 · 引用溯源", "success");
        void track(
            () => api.settings.update({ autoSync: true, deepSearch: true, citations: true }),
            { error: "推荐配置同步失败" },
        );
    };

    const handleCreate = async () => {
        if (!projectName.trim()) {
            notify("请先输入项目名称", "error");
            return;
        }
        const result = await track(
            () =>
                api.projects.create({
                    name: projectName.trim(),
                    template,
                    team,
                    visibility,
                }),
            {
                loading: "正在创建项目...",
                success: "项目创建成功，正在进入工作区",
            },
        );
        if (result) {
            setCurrentProject({ id: result.item.id, name: result.item.name });
            navigate("/frame2688", {
                state: { projectId: result.item.id, projectName: result.item.name },
            });
        }
    };

    return (
        <div className="scroll-container">
            {searchOpen ? <QuickSearch onClose={() => setSearchOpen(false)} /> : null}
            <div
                id="2_319"
                className="Pixso-frame-2_319 pixso-relative-no-shrink pixso-flex"
            >
                <div className="frame-content-2_319 pixso-relative-flex">
                    <div
                        id="2_320"
                        className="stroke-wrapper-2_320 pixso-relative-no-shrink pixso-flex"
                    >
                        <div className="Pixso-frame-2_320 pixso-relative-no-shrink pixso-flex"></div>
                        <div className="stroke-2_320"></div>
                        <div className="Pixso-frame-2_320-content-layer">
                            <div className="frame-content-2_320 pixso-relative-flex">
                                <div
                                    id="2_321"
                                    className="Pixso-frame-2_321 pixso-relative-no-shrink pixso-flex"
                                >
                                    <div className="frame-content-2_321 pixso-relative-flex">
                                        <div
                                            id="2_322"
                                            className="Pixso-frame-2_322 pixso-relative-no-shrink pixso-flex"
                                        >
                                            <div className="frame-content-2_322 pixso-relative-flex">
                                                <div
                                                    id="2_323"
                                                    className="Pixso-vector-2_323 pixso-relative-no-shrink"
                                                ></div>
                                            </div>
                                        </div>
                                        <div
                                            id="2_337"
                                            className="Pixso-frame-2_337 pixso-relative-flex"
                                        >
                                            <div className="frame-content-2_337 pixso-relative-flex">
                                                <p
                                                    id="2_338"
                                                    className="Pixso-paragraph-2_338 pixso-relative-auto-size pixso-flex-shrink-0"
                                                    {...navTo(navigate, "/frame2688")}
                                                >
                                                    {"HyperCortex"}
                                                </p>
                                                <p
                                                    id="2_339"
                                                    className="Pixso-paragraph-2_339 pixso-relative-auto-size pixso-flex-shrink-0"
                                                >
                                                    {"企业知识智能平台"}
                                                </p>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                                <div
                                    id="2_340"
                                    className="Pixso-frame-2_340 pixso-relative-no-shrink pixso-flex"
                                >
                                    <div className="frame-content-2_340 pixso-relative-flex">
                                        <div
                                            id="2_341"
                                            className="Pixso-frame-2_341 pixso-relative-no-shrink pixso-flex"
                                        >
                                            <div className="frame-content-2_341 pixso-relative-flex">
                                                <div
                                                    id="2_342"
                                                    className="Pixso-frame-2_342 pixso-relative-no-shrink"
                                                >
                                                    <div
                                                        id="2_343"
                                                        className="stroke-wrapper-2_343"
                                                    >
                                                        <div className="Pixso-rectangle-2_343 pixso-position-relative"></div>
                                                        <div className="stroke-2_343"></div>
                                                    </div>
                                                    <div
                                                        id="2_344"
                                                        className="stroke-wrapper-2_344"
                                                    >
                                                        <div className="Pixso-rectangle-2_344 pixso-position-relative"></div>
                                                        <div className="stroke-2_344"></div>
                                                    </div>
                                                    <div
                                                        id="2_345"
                                                        className="stroke-wrapper-2_345"
                                                    >
                                                        <div className="Pixso-rectangle-2_345 pixso-position-relative"></div>
                                                        <div className="stroke-2_345"></div>
                                                    </div>
                                                    <div
                                                        id="2_346"
                                                        className="stroke-wrapper-2_346"
                                                    >
                                                        <div className="Pixso-rectangle-2_346 pixso-position-relative"></div>
                                                        <div className="stroke-2_346"></div>
                                                    </div>
                                                </div>
                                                <p
                                                    id="2_347"
                                                    className="Pixso-paragraph-2_347 pixso-position-relative pixso-h-auto"
                                                    {...navTo(navigate, "/frame2688")}
                                                >
                                                    {"工作区"}
                                                </p>
                                                <div
                                                    id="2_348"
                                                    className="Pixso-rectangle-2_348 pixso-relative-no-shrink"
                                                ></div>
                                            </div>
                                        </div>
                                        <div
                                            id="2_349"
                                            className="Pixso-frame-2_349 pixso-relative-no-shrink pixso-flex"
                                        >
                                            <div className="frame-content-2_349 pixso-relative-flex">
                                                <div
                                                    id="2_350"
                                                    className="Pixso-vector-2_350 pixso-relative-no-shrink"
                                                ></div>
                                                <p
                                                    id="2_355"
                                                    className="Pixso-paragraph-2_355 pixso-position-relative pixso-h-auto"
                                                    {...navTo(navigate, "/frame2688")}
                                                >
                                                    {"知识地图"}
                                                </p>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                                <div
                                    id="2_356"
                                    className="Pixso-frame-2_356 pixso-relative-no-shrink pixso-flex"
                                >
                                    <div className="frame-content-2_356 pixso-relative-flex">
                                        <div
                                            id="2_357"
                                            className="Pixso-vector-2_357 pixso-relative-no-shrink"
                                        ></div>
                                        <p
                                            id="2_360"
                                            className="Pixso-paragraph-2_360 pixso-position-relative pixso-h-auto"
                                            {...navTo(navigate, "/")}
                                        >
                                            {"新建项目"}
                                        </p>
                                        <div
                                            id="2_361"
                                            className="Pixso-frame-2_361 pixso-relative-no-shrink pixso-flex"
                                        >
                                            <div className="frame-content-2_361 pixso-relative-flex">
                                                <p
                                                    id="2_362"
                                                    className="Pixso-paragraph-2_362 pixso-relative-auto-size pixso-flex-shrink-0"
                                                >
                                                    {"⌘N"}
                                                </p>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                                <div
                                    id="2_363"
                                    className="Pixso-frame-2_363 pixso-relative-no-shrink pixso-flex-auto-height"
                                >
                                    <div className="frame-content-2_363 pixso-relative-flex">
                                        <div
                                            id="2_364"
                                            className="Pixso-frame-2_364 pixso-relative-no-shrink pixso-flex"
                                        >
                                            <div className="frame-content-2_364 pixso-relative-flex">
                                                <p
                                                    id="2_365"
                                                    className="Pixso-paragraph-2_365 pixso-relative-auto-size pixso-flex-shrink-0"
                                                >
                                                    {"我的项目"}
                                                </p>
                                                <p
                                                    id="2_366"
                                                    className="Pixso-paragraph-2_366 pixso-relative-auto-size pixso-flex-shrink-0"
                                                >
                                                    {"12"}
                                                </p>
                                            </div>
                                        </div>
                                        <ProjectSidebarList currentProjectId={getCurrentProject().id} />
                                        <div
                                            id="2_367"
                                            className="stroke-wrapper-2_367 pixso-relative-no-shrink pixso-flex"
                                        >
                                            <div className="Pixso-frame-2_367 pixso-relative-no-shrink pixso-flex">
                                                <div className="frame-content-2_367 pixso-relative-flex">
                                                    <div
                                                        id="2_368"
                                                        className="Pixso-frame-2_368 pixso-relative-no-shrink pixso-flex"
                                                    ></div>
                                                    <div
                                                        id="2_369"
                                                        className="Pixso-frame-2_369 pixso-relative-flex"
                                                    >
                                                        <div className="frame-content-2_369 pixso-relative-flex">
                                                            <p
                                                                id="2_370"
                                                                className="Pixso-paragraph-2_370 pixso-relative-no-shrink pixso-h-auto"
                                                                {...navTo(navigate, "/frame2688")}
                                                            >
                                                                {"产品知识中枢"}
                                                            </p>
                                                            <p
                                                                id="2_371"
                                                                className="Pixso-paragraph-2_371 pixso-relative-no-shrink pixso-h-auto"
                                                            >
                                                                {"128 份资料"}
                                                            </p>
                                                        </div>
                                                    </div>
                                                    <div
                                                        id="2_372"
                                                        className="Pixso-vector-2_372 pixso-relative-no-shrink"
                                                    ></div>
                                                </div>
                                            </div>
                                            <div className="stroke-2_367"></div>
                                        </div>
                                        <div
                                            id="2_374"
                                            className="stroke-wrapper-2_374 pixso-relative-no-shrink pixso-flex"
                                        >
                                            <div className="Pixso-frame-2_374 pixso-relative-no-shrink pixso-flex">
                                                <div className="frame-content-2_374 pixso-relative-flex">
                                                    <div
                                                        id="2_375"
                                                        className="Pixso-frame-2_375 pixso-relative-no-shrink pixso-flex"
                                                    ></div>
                                                    <div
                                                        id="2_376"
                                                        className="Pixso-frame-2_376 pixso-relative-flex"
                                                    >
                                                        <div className="frame-content-2_376 pixso-relative-flex">
                                                            <p
                                                                id="2_377"
                                                                className="Pixso-paragraph-2_377 pixso-relative-no-shrink pixso-h-auto"
                                                            >
                                                                {
                                                                    "临床研究资料库"
                                                                }
                                                            </p>
                                                            <p
                                                                id="2_378"
                                                                className="Pixso-paragraph-2_378 pixso-relative-no-shrink pixso-h-auto"
                                                            >
                                                                {"86 份资料"}
                                                            </p>
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>
                                            <div className="stroke-2_374"></div>
                                        </div>
                                        <div
                                            id="2_379"
                                            className="stroke-wrapper-2_379 pixso-relative-no-shrink pixso-flex"
                                        >
                                            <div className="Pixso-frame-2_379 pixso-relative-no-shrink pixso-flex">
                                                <div className="frame-content-2_379 pixso-relative-flex">
                                                    <div
                                                        id="2_380"
                                                        className="Pixso-frame-2_380 pixso-relative-no-shrink pixso-flex"
                                                    ></div>
                                                    <div
                                                        id="2_381"
                                                        className="Pixso-frame-2_381 pixso-relative-flex"
                                                    >
                                                        <div className="frame-content-2_381 pixso-relative-flex">
                                                            <p
                                                                id="2_382"
                                                                className="Pixso-paragraph-2_382 pixso-relative-no-shrink pixso-h-auto"
                                                            >
                                                                {"法务合规中心"}
                                                            </p>
                                                            <p
                                                                id="2_383"
                                                                className="Pixso-paragraph-2_383 pixso-relative-no-shrink pixso-h-auto"
                                                            >
                                                                {"43 份资料"}
                                                            </p>
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>
                                            <div className="stroke-2_379"></div>
                                        </div>
                                        <div
                                            id="2_384"
                                            className="stroke-wrapper-2_384 pixso-relative-no-shrink pixso-flex"
                                        >
                                            <div className="Pixso-frame-2_384 pixso-relative-no-shrink pixso-flex">
                                                <div className="frame-content-2_384 pixso-relative-flex">
                                                    <div
                                                        id="2_385"
                                                        className="Pixso-frame-2_385 pixso-relative-no-shrink pixso-flex"
                                                    ></div>
                                                    <div
                                                        id="2_386"
                                                        className="Pixso-frame-2_386 pixso-relative-flex"
                                                    >
                                                        <div className="frame-content-2_386 pixso-relative-flex">
                                                            <p
                                                                id="2_387"
                                                                className="Pixso-paragraph-2_387 pixso-relative-no-shrink pixso-h-auto"
                                                            >
                                                                {
                                                                    "供应链运营手册"
                                                                }
                                                            </p>
                                                            <p
                                                                id="2_388"
                                                                className="Pixso-paragraph-2_388 pixso-relative-no-shrink pixso-h-auto"
                                                            >
                                                                {"61 份资料"}
                                                            </p>
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>
                                            <div className="stroke-2_384"></div>
                                        </div>
                                        <div
                                            id="2_389"
                                            className="Pixso-frame-2_389 pixso-relative-no-shrink pixso-flex"
                                        >
                                            <div className="frame-content-2_389 pixso-relative-flex">
                                                <div
                                                    id="2_390"
                                                    className="Pixso-vector-2_390 pixso-relative-no-shrink"
                                                ></div>
                                                <p
                                                    id="2_393"
                                                    className="Pixso-paragraph-2_393 pixso-position-relative pixso-h-auto"
                                                    {...navTo(navigate, "/frame2688")}
                                                >
                                                    {"查看全部 12 个项目"}
                                                </p>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                                <div
                                    id="2_394"
                                    className="stroke-wrapper-2_394 pixso-relative-no-shrink pixso-flex"
                                >
                                    <div className="Pixso-frame-2_394 pixso-relative-no-shrink pixso-flex">
                                        <div className="frame-content-2_394 pixso-relative-flex">
                                            <div
                                                id="2_395"
                                                className="Pixso-frame-2_395 pixso-relative-no-shrink pixso-flex"
                                            >
                                                <div className="frame-content-2_395 pixso-relative-flex">
                                                    <p
                                                        id="2_396"
                                                        className="Pixso-paragraph-2_396 pixso-relative-auto-size pixso-flex-shrink-0"
                                                    >
                                                        {"知识容量"}
                                                    </p>
                                                    <p
                                                        id="2_397"
                                                        className="Pixso-paragraph-2_397 pixso-relative-auto-size pixso-flex-shrink-0"
                                                    >
                                                        {"64%"}
                                                    </p>
                                                </div>
                                            </div>
                                            <div
                                                id="2_398"
                                                className="Pixso-frame-2_398 pixso-relative-no-shrink pixso-flex"
                                            >
                                                <div className="frame-content-2_398 pixso-relative-flex">
                                                    <div
                                                        id="2_399"
                                                        className="Pixso-frame-2_399 pixso-relative-no-shrink pixso-flex"
                                                    ></div>
                                                </div>
                                            </div>
                                            <p
                                                id="2_400"
                                                className="Pixso-paragraph-2_400 pixso-relative-no-shrink pixso-h-auto"
                                            >
                                                {"12.8 GB / 20 GB · 升级可扩展"}
                                            </p>
                                        </div>
                                    </div>
                                    <div className="stroke-2_394"></div>
                                </div>
                                <div
                                    id="2_401"
                                    className="Pixso-frame-2_401 pixso-relative-no-shrink pixso-flex"
                                >
                                    <div className="frame-content-2_401 pixso-relative-flex">
                                        <div
                                            id="2_402"
                                            className="Pixso-frame-2_402 pixso-relative-no-shrink pixso-flex"
                                        >
                                            <div className="frame-content-2_402 pixso-relative-flex">
                                                <p
                                                    id="2_403"
                                                    className="Pixso-paragraph-2_403 pixso-relative-auto-size pixso-flex-shrink-0"
                                                >
                                                    {"林"}
                                                </p>
                                            </div>
                                        </div>
                                        <div
                                            id="2_404"
                                            className="Pixso-frame-2_404 pixso-relative-flex"
                                        >
                                            <div className="frame-content-2_404 pixso-relative-flex">
                                                <p
                                                    id="2_405"
                                                    className="Pixso-paragraph-2_405 pixso-relative-no-shrink pixso-h-auto"
                                                >
                                                    {"林书瑶"}
                                                </p>
                                                <p
                                                    id="2_406"
                                                    className="Pixso-paragraph-2_406 pixso-relative-no-shrink pixso-h-auto"
                                                >
                                                    {"产品知识负责人"}
                                                </p>
                                            </div>
                                        </div>
                                        <div
                                            id="2_407"
                                            className="Pixso-vector-2_407 pixso-relative-no-shrink"
                                        ></div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    <div
                        id="2_412"
                        className="Pixso-frame-2_412 pixso-relative-flex"
                    >
                        <div className="frame-content-2_412 pixso-relative-flex">
                            <div
                                id="2_413"
                                className="Pixso-frame-2_413 pixso-relative-no-shrink pixso-flex"
                            >
                                <div className="frame-content-2_413 pixso-relative-flex">
                                    <div
                                        id="2_414"
                                        className="Pixso-frame-2_414 pixso-relative-no-shrink pixso-flex"
                                    >
                                        <div className="frame-content-2_414 pixso-relative-flex">
                                            <p
                                                id="2_415"
                                                className="Pixso-paragraph-2_415 pixso-relative-auto-size pixso-flex-shrink-0"
                                                {...navTo(navigate, "/frame2688")}
                                            >
                                                {"工作区"}
                                            </p>
                                            <div
                                                id="2_416"
                                                className="Pixso-vector-2_416 pixso-relative-no-shrink"
                                            ></div>
                                            <p
                                                id="2_418"
                                                className="Pixso-paragraph-2_418 pixso-relative-auto-size pixso-flex-shrink-0"
                                                {...navTo(navigate, "/frame2688")}
                                            >
                                                {"新建项目"}
                                            </p>
                                        </div>
                                    </div>
                                    <div
                                        id="2_419"
                                        className="Pixso-frame-2_419 pixso-relative-no-shrink pixso-flex"
                                    >
                                        <div className="frame-content-2_419 pixso-relative-flex">
                                            <div
                                                id="2_420"
                                                className="stroke-wrapper-2_420 pixso-relative-no-shrink pixso-flex"
                                                {...pressable(() => setSearchOpen(true))}
                                            >
                                                <div className="Pixso-frame-2_420 pixso-relative-no-shrink pixso-flex">
                                                    <div className="frame-content-2_420 pixso-relative-flex">
                                                        <div
                                                            id="2_421"
                                                            className="Pixso-vector-2_421 pixso-relative-no-shrink"
                                                        ></div>
                                                        <p
                                                            id="2_424"
                                                            className="Pixso-paragraph-2_424 pixso-position-relative pixso-h-auto"
                                                        >
                                                            {
                                                                "搜索项目、资料、问答"
                                                            }
                                                        </p>
                                                        <p
                                                            id="2_425"
                                                            className="Pixso-paragraph-2_425 pixso-relative-auto-size pixso-flex-shrink-0"
                                                        >
                                                            {"⌘K"}
                                                        </p>
                                                    </div>
                                                </div>
                                                <div className="stroke-2_420"></div>
                                            </div>
                                            <div
                                                id="2_426"
                                                className="stroke-wrapper-2_426 pixso-relative-no-shrink pixso-flex"
                                                {...pressable(async () => {
                                                    const data = await track(() => api.notifications.list(), {
                                                        error: "通知加载失败",
                                                    });
                                                    if (data) {
                                                        const unread = data.items.filter((item) => !item.read).length;
                                                        notify(unread ? `有 ${unread} 条未读通知` : "暂无新通知", "success");
                                                    }
                                                })}
                                            >
                                                <div className="Pixso-frame-2_426 pixso-relative-no-shrink pixso-flex">
                                                    <div className="frame-content-2_426 pixso-relative-flex">
                                                        <div
                                                            id="2_427"
                                                            className="Pixso-vector-2_427 pixso-relative-no-shrink"
                                                        ></div>
                                                    </div>
                                                </div>
                                                <div className="stroke-2_426"></div>
                                            </div>
                                            <div
                                                id="2_430"
                                                className="stroke-wrapper-2_430 pixso-relative-no-shrink pixso-flex"
                                                {...pressable(() => notify("帮助中心（演示）"))}
                                            >
                                                <div className="Pixso-frame-2_430 pixso-relative-no-shrink pixso-flex">
                                                    <div className="frame-content-2_430 pixso-relative-flex">
                                                        <div
                                                            id="2_431"
                                                            className="Pixso-vector-2_431 pixso-relative-no-shrink"
                                                        ></div>
                                                    </div>
                                                </div>
                                                <div className="stroke-2_430"></div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            <div
                                id="2_435"
                                className="Pixso-frame-2_435 pixso-relative-no-shrink pixso-flex"
                            >
                                <div className="frame-content-2_435 pixso-relative-flex">
                                    <div
                                        id="2_436"
                                        className="Pixso-frame-2_436 pixso-relative-no-shrink pixso-flex"
                                    >
                                        <div className="frame-content-2_436 pixso-relative-flex">
                                            <div
                                                id="2_437"
                                                className="Pixso-frame-2_437 pixso-relative-no-shrink pixso-flex"
                                            >
                                                <div className="frame-content-2_437 pixso-relative-flex">
                                                    <div
                                                        id="2_438"
                                                        className="Pixso-vector-2_438 pixso-relative-no-shrink"
                                                    ></div>
                                                    <p
                                                        id="2_443"
                                                        className="Pixso-paragraph-2_443 pixso-relative-auto-size pixso-flex-shrink-0"
                                                    >
                                                        {"新项目"}
                                                    </p>
                                                </div>
                                            </div>
                                            <p
                                                id="2_444"
                                                className="Pixso-paragraph-2_444 pixso-relative-auto-size pixso-flex-shrink-0"
                                            >
                                                {
                                                    "约 2 分钟完成配置，随时可调整"
                                                }
                                            </p>
                                        </div>
                                    </div>
                                    <p
                                        id="2_445"
                                        className="Pixso-paragraph-2_445 pixso-relative-no-shrink pixso-h-auto"
                                    >
                                        {"创建一个新的知识项目"}
                                    </p>
                                    <p
                                        id="2_446"
                                        className="Pixso-paragraph-2_446 pixso-relative-no-shrink pixso-h-auto"
                                    >
                                        {
                                            "把散落在云盘、邮件与工单里的企业资料汇聚成可问答的知识中枢。选择模板，命名项目，HyperCortex 会自动完成解析、切片与向量索引。"
                                        }
                                    </p>
                                </div>
                            </div>
                            <div
                                id="2_447"
                                className="Pixso-frame-2_447 pixso-relative-no-shrink pixso-flex"
                            >
                                <div className="frame-content-2_447 pixso-relative-flex">
                                    <div
                                        id="2_448"
                                        className="stroke-wrapper-2_448 pixso-relative-flex"
                                    >
                                        <div className="Pixso-frame-2_448 pixso-relative-flex">
                                            <div className="frame-content-2_448 pixso-relative-flex">
                                                <div
                                                    id="2_449"
                                                    className="Pixso-frame-2_449 pixso-relative-no-shrink pixso-flex"
                                                >
                                                    <div className="frame-content-2_449 pixso-relative-flex">
                                                        <div
                                                            id="2_450"
                                                            className="Pixso-frame-2_450 pixso-relative-flex"
                                                            {...pressable(() => notify("当前步骤：选择模板"))}
                                                        >
                                                            <div className="frame-content-2_450 pixso-relative-flex">
                                                                <div
                                                                    id="2_451"
                                                                    className="stroke-wrapper-2_451 pixso-relative-no-shrink pixso-flex"
                                                                >
                                                                    <div className="Pixso-frame-2_451 pixso-relative-no-shrink pixso-flex">
                                                                        <div className="frame-content-2_451 pixso-relative-flex">
                                                                            <p
                                                                                id="2_452"
                                                                                className="Pixso-paragraph-2_452 pixso-relative-auto-size pixso-flex-shrink-0"
                                                                            >
                                                                                {
                                                                                    "1"
                                                                                }
                                                                            </p>
                                                                        </div>
                                                                    </div>
                                                                    <div className="stroke-2_451"></div>
                                                                </div>
                                                                <p
                                                                    id="2_453"
                                                                    className="Pixso-paragraph-2_453 pixso-relative-auto-size pixso-flex-shrink-0"
                                                                >
                                                                    {"选择模板"}
                                                                </p>
                                                                <div
                                                                    id="2_454"
                                                                    className="Pixso-vector-2_454 pixso-position-relative"
                                                                ></div>
                                                            </div>
                                                        </div>
                                                        <div
                                                            id="2_455"
                                                            className="Pixso-frame-2_455 pixso-relative-flex"
                                                            {...pressable(() => notify("当前步骤：基本信息"))}
                                                        >
                                                            <div className="frame-content-2_455 pixso-relative-flex">
                                                                <div
                                                                    id="2_456"
                                                                    className="stroke-wrapper-2_456 pixso-relative-no-shrink pixso-flex"
                                                                >
                                                                    <div className="Pixso-frame-2_456 pixso-relative-no-shrink pixso-flex">
                                                                        <div className="frame-content-2_456 pixso-relative-flex">
                                                                            <p
                                                                                id="2_457"
                                                                                className="Pixso-paragraph-2_457 pixso-relative-auto-size pixso-flex-shrink-0"
                                                                            >
                                                                                {
                                                                                    "2"
                                                                                }
                                                                            </p>
                                                                        </div>
                                                                    </div>
                                                                    <div className="stroke-2_456"></div>
                                                                </div>
                                                                <p
                                                                    id="2_458"
                                                                    className="Pixso-paragraph-2_458 pixso-relative-auto-size pixso-flex-shrink-0"
                                                                >
                                                                    {"基本信息"}
                                                                </p>
                                                                <div
                                                                    id="2_459"
                                                                    className="Pixso-vector-2_459 pixso-position-relative"
                                                                ></div>
                                                            </div>
                                                        </div>
                                                        <div
                                                            id="2_460"
                                                            className="Pixso-frame-2_460 pixso-relative-flex"
                                                            {...pressable(() => notify("当前步骤：上传资料"))}
                                                        >
                                                            <div className="frame-content-2_460 pixso-relative-flex">
                                                                <div
                                                                    id="2_461"
                                                                    className="stroke-wrapper-2_461 pixso-relative-no-shrink pixso-flex"
                                                                >
                                                                    <div className="Pixso-frame-2_461 pixso-relative-no-shrink pixso-flex">
                                                                        <div className="frame-content-2_461 pixso-relative-flex">
                                                                            <p
                                                                                id="2_462"
                                                                                className="Pixso-paragraph-2_462 pixso-relative-auto-size pixso-flex-shrink-0"
                                                                            >
                                                                                {
                                                                                    "3"
                                                                                }
                                                                            </p>
                                                                        </div>
                                                                    </div>
                                                                    <div className="stroke-2_461"></div>
                                                                </div>
                                                                <p
                                                                    id="2_463"
                                                                    className="Pixso-paragraph-2_463 pixso-relative-auto-size pixso-flex-shrink-0"
                                                                >
                                                                    {"上传资料"}
                                                                </p>
                                                                <div
                                                                    id="2_464"
                                                                    className="Pixso-vector-2_464 pixso-position-relative"
                                                                ></div>
                                                            </div>
                                                        </div>
                                                        <div
                                                            id="2_465"
                                                            className="Pixso-frame-2_465 pixso-relative-no-shrink pixso-flex"
                                                            {...pressable(() => notify("当前步骤：完成"))}
                                                        >
                                                            <div className="frame-content-2_465 pixso-relative-flex">
                                                                <div
                                                                    id="2_466"
                                                                    className="stroke-wrapper-2_466 pixso-relative-no-shrink pixso-flex"
                                                                >
                                                                    <div className="Pixso-frame-2_466 pixso-relative-no-shrink pixso-flex">
                                                                        <div className="frame-content-2_466 pixso-relative-flex">
                                                                            <p
                                                                                id="2_467"
                                                                                className="Pixso-paragraph-2_467 pixso-relative-auto-size pixso-flex-shrink-0"
                                                                            >
                                                                                {
                                                                                    "4"
                                                                                }
                                                                            </p>
                                                                        </div>
                                                                    </div>
                                                                    <div className="stroke-2_466"></div>
                                                                </div>
                                                                <p
                                                                    id="2_468"
                                                                    className="Pixso-paragraph-2_468 pixso-relative-auto-size pixso-flex-shrink-0"
                                                                >
                                                                    {"完成"}
                                                                </p>
                                                            </div>
                                                        </div>
                                                    </div>
                                                </div>
                                                <div
                                                    id="2_469"
                                                    className="Pixso-frame-2_469 pixso-relative-no-shrink pixso-flex"
                                                >
                                                    <div className="frame-content-2_469 pixso-relative-flex">
                                                        <div
                                                            id="2_470"
                                                            className="Pixso-frame-2_470 pixso-relative-no-shrink pixso-flex"
                                                        >
                                                            <div className="frame-content-2_470 pixso-relative-flex">
                                                                <p
                                                                    id="2_471"
                                                                    className="Pixso-paragraph-2_471 pixso-relative-auto-size pixso-flex-shrink-0"
                                                                >
                                                                    {"项目名称"}
                                                                </p>
                                                                <p
                                                                    id="2_472"
                                                                    className="Pixso-paragraph-2_472 pixso-relative-auto-size pixso-flex-shrink-0"
                                                                >
                                                                    {"*"}
                                                                </p>
                                                            </div>
                                                        </div>
                                                        <div
                                                            id="2_473"
                                                            className="stroke-wrapper-2_473 pixso-relative-no-shrink pixso-flex"
                                                        >
                                                            <div className="Pixso-frame-2_473 pixso-relative-no-shrink pixso-flex">
                                                                <div className="frame-content-2_473 pixso-relative-flex">
                                                                    <div
                                                                        id="2_474"
                                                                        className="Pixso-vector-2_474 pixso-relative-no-shrink"
                                                                    ></div>
                                                                    <p
                                                                        id="2_479"
                                                                        className="Pixso-paragraph-2_479 pixso-position-relative pixso-h-auto hc-editable"
                                                                        data-placeholder="请输入项目名称"
                                                                        contentEditable
                                                                        suppressContentEditableWarning
                                                                        onInput={(event) =>
                                                                            setProjectName(event.currentTarget.textContent ?? "")
                                                                        }
                                                                    >
                                                                        {""}
                                                                    </p>
                                                                    <p
                                                                        id="2_480"
                                                                        className="Pixso-paragraph-2_480 pixso-relative-auto-size pixso-flex-shrink-0"
                                                                    >
                                                                        {`${projectName.length}/40`}
                                                                    </p>
                                                                </div>
                                                            </div>
                                                            <div className="stroke-2_473"></div>
                                                        </div>
                                                        <p
                                                            id="2_481"
                                                            className="Pixso-paragraph-2_481 pixso-relative-no-shrink pixso-h-auto"
                                                        >
                                                            {
                                                                "建议包含时间范围与资料来源，便于团队识别。"
                                                            }
                                                        </p>
                                                    </div>
                                                </div>
                                                <div
                                                    id="2_482"
                                                    className="Pixso-frame-2_482 pixso-relative-no-shrink pixso-flex"
                                                >
                                                    <div className="frame-content-2_482 pixso-relative-flex">
                                                        <div
                                                            id="2_483"
                                                            className="Pixso-frame-2_483 pixso-relative-no-shrink pixso-flex"
                                                        >
                                                            <div className="frame-content-2_483 pixso-relative-flex">
                                                                <p
                                                                    id="2_484"
                                                                    className="Pixso-paragraph-2_484 pixso-relative-auto-size pixso-flex-shrink-0"
                                                                >
                                                                    {"知识模板"}
                                                                </p>
                                                                <div
                                                                    id="2_485"
                                                                    className="Pixso-frame-2_485 pixso-relative-no-shrink pixso-flex"
                                                                >
                                                                    <div className="frame-content-2_485 pixso-relative-flex">
                                                                        <div
                                                                            id="2_486"
                                                                            className="Pixso-vector-2_486 pixso-relative-no-shrink"
                                                                        ></div>
                                                                        <p
                                                                            id="2_490"
                                                                            className="Pixso-paragraph-2_490 pixso-relative-auto-size pixso-flex-shrink-0"
                                                                        >
                                                                            {
                                                                                "模板决定默认切片与检索策略"
                                                                            }
                                                                        </p>
                                                                    </div>
                                                                </div>
                                                            </div>
                                                        </div>
                                                        <div
                                                            id="2_491"
                                                            className="Pixso-frame-2_491 pixso-relative-no-shrink pixso-flex"
                                                        >
                                                            <div className="frame-content-2_491 pixso-relative-flex">
                                                                <div
                                                                    id="2_492"
                                                                    className={`stroke-wrapper-2_492 pixso-relative-flex${template === "产品知识库" ? " hc-selected" : ""}`}
                                                                    {...pressable(() => selectTemplate("产品知识库"))}
                                                                >
                                                                    <div className="Pixso-frame-2_492 pixso-relative-flex">
                                                                        <div className="frame-content-2_492 pixso-relative-flex">
                                                                            <div
                                                                                id="2_493"
                                                                                className="Pixso-frame-2_493 pixso-relative-no-shrink pixso-flex"
                                                                            >
                                                                                <div className="frame-content-2_493 pixso-relative-flex">
                                                                                    <div
                                                                                        id="2_494"
                                                                                        className="Pixso-frame-2_494 pixso-relative-no-shrink pixso-flex"
                                                                                    >
                                                                                        <div className="frame-content-2_494 pixso-relative-flex">
                                                                                            <div
                                                                                                id="2_495"
                                                                                                className="Pixso-vector-2_495 pixso-relative-no-shrink"
                                                                                            ></div>
                                                                                        </div>
                                                                                    </div>
                                                                                    <div
                                                                                        id="2_500"
                                                                                        className="Pixso-vector-2_500 pixso-relative-no-shrink"
                                                                                    ></div>
                                                                                </div>
                                                                            </div>
                                                                            <p
                                                                                id="2_503"
                                                                                className="Pixso-paragraph-2_503 pixso-relative-no-shrink pixso-h-auto"
                                                                            >
                                                                                {
                                                                                    "产品知识库"
                                                                                }
                                                                            </p>
                                                                            <p
                                                                                id="2_504"
                                                                                className="Pixso-paragraph-2_504 pixso-relative-no-shrink pixso-h-auto"
                                                                            >
                                                                                {
                                                                                    "需求、竞品、路线图与发布说明"
                                                                                }
                                                                            </p>
                                                                        </div>
                                                                    </div>
                                                                    <div className="stroke-2_492"></div>
                                                                </div>
                                                                <div
                                                                    id="2_505"
                                                                    className={`stroke-wrapper-2_505 pixso-relative-flex${template === "研究报告库" ? " hc-selected" : ""}`}
                                                                    {...pressable(() => selectTemplate("研究报告库"))}
                                                                >
                                                                    <div className="Pixso-frame-2_505 pixso-relative-flex">
                                                                        <div className="frame-content-2_505 pixso-relative-flex">
                                                                            <div
                                                                                id="2_506"
                                                                                className="Pixso-frame-2_506 pixso-relative-no-shrink pixso-flex"
                                                                            >
                                                                                <div className="frame-content-2_506 pixso-relative-flex">
                                                                                    <div
                                                                                        id="2_507"
                                                                                        className="Pixso-frame-2_507 pixso-relative-no-shrink pixso-flex"
                                                                                    >
                                                                                        <div className="frame-content-2_507 pixso-relative-flex">
                                                                                            <div
                                                                                                id="2_508"
                                                                                                className="Pixso-vector-2_508 pixso-relative-no-shrink"
                                                                                            ></div>
                                                                                        </div>
                                                                                    </div>
                                                                                    <div
                                                                                        id="2_514"
                                                                                        className="stroke-wrapper-2_514 pixso-relative-no-shrink"
                                                                                    >
                                                                                        <div className="Pixso-rectangle-2_514 pixso-relative-no-shrink"></div>
                                                                                        <div className="stroke-2_514"></div>
                                                                                    </div>
                                                                                </div>
                                                                            </div>
                                                                            <p
                                                                                id="2_515"
                                                                                className="Pixso-paragraph-2_515 pixso-relative-no-shrink pixso-h-auto"
                                                                            >
                                                                                {
                                                                                    "研究报告库"
                                                                                }
                                                                            </p>
                                                                            <p
                                                                                id="2_516"
                                                                                className="Pixso-paragraph-2_516 pixso-relative-no-shrink pixso-h-auto"
                                                                            >
                                                                                {
                                                                                    "论文、访谈与市场分析"
                                                                                }
                                                                            </p>
                                                                        </div>
                                                                    </div>
                                                                    <div className="stroke-2_505"></div>
                                                                </div>
                                                                <div
                                                                    id="2_517"
                                                                    className={`stroke-wrapper-2_517 pixso-relative-flex${template === "合规制度库" ? " hc-selected" : ""}`}
                                                                    {...pressable(() => selectTemplate("合规制度库"))}
                                                                >
                                                                    <div className="Pixso-frame-2_517 pixso-relative-flex">
                                                                        <div className="frame-content-2_517 pixso-relative-flex">
                                                                            <div
                                                                                id="2_518"
                                                                                className="Pixso-frame-2_518 pixso-relative-no-shrink pixso-flex"
                                                                            >
                                                                                <div className="frame-content-2_518 pixso-relative-flex">
                                                                                    <div
                                                                                        id="2_519"
                                                                                        className="Pixso-frame-2_519 pixso-relative-no-shrink pixso-flex"
                                                                                    >
                                                                                        <div className="frame-content-2_519 pixso-relative-flex">
                                                                                            <div
                                                                                                id="2_520"
                                                                                                className="Pixso-vector-2_520 pixso-relative-no-shrink"
                                                                                            ></div>
                                                                                        </div>
                                                                                    </div>
                                                                                    <div
                                                                                        id="2_523"
                                                                                        className="stroke-wrapper-2_523 pixso-relative-no-shrink"
                                                                                    >
                                                                                        <div className="Pixso-rectangle-2_523 pixso-relative-no-shrink"></div>
                                                                                        <div className="stroke-2_523"></div>
                                                                                    </div>
                                                                                </div>
                                                                            </div>
                                                                            <p
                                                                                id="2_524"
                                                                                className="Pixso-paragraph-2_524 pixso-relative-no-shrink pixso-h-auto"
                                                                            >
                                                                                {
                                                                                    "合规制度库"
                                                                                }
                                                                            </p>
                                                                            <p
                                                                                id="2_525"
                                                                                className="Pixso-paragraph-2_525 pixso-relative-no-shrink pixso-h-auto"
                                                                            >
                                                                                {
                                                                                    "制度文件与审计问答"
                                                                                }
                                                                            </p>
                                                                        </div>
                                                                    </div>
                                                                    <div className="stroke-2_517"></div>
                                                                </div>
                                                            </div>
                                                        </div>
                                                    </div>
                                                </div>
                                                <div
                                                    id="2_526"
                                                    className="Pixso-frame-2_526 pixso-relative-no-shrink pixso-flex"
                                                >
                                                    <div className="frame-content-2_526 pixso-relative-flex">
                                                        <div
                                                            id="2_527"
                                                            className="Pixso-frame-2_527 pixso-relative-flex"
                                                        >
                                                            <div className="frame-content-2_527 pixso-relative-flex">
                                                                <p
                                                                    id="2_528"
                                                                    className="Pixso-paragraph-2_528 pixso-relative-no-shrink pixso-h-auto"
                                                                >
                                                                    {"所属团队"}
                                                                </p>
                                                                <div
                                                                    id="2_529"
                                                                    className="stroke-wrapper-2_529 pixso-relative-no-shrink pixso-flex"
                                                                >
                                                                    <div
                                                                        className="Pixso-frame-2_529 pixso-relative-no-shrink pixso-flex"
                                                                        {...pressable(cycleTeam)}
                                                                    >
                                                                        <div className="frame-content-2_529 pixso-relative-flex">
                                                                            <div
                                                                                id="2_530"
                                                                                className="Pixso-vector-2_530 pixso-relative-no-shrink"
                                                                            ></div>
                                                                            <p
                                                                                id="2_535"
                                                                                className="Pixso-paragraph-2_535 pixso-position-relative pixso-h-auto"
                                                                            >
                                                                                {team}
                                                                            </p>
                                                                            <div
                                                                                id="2_536"
                                                                                className="Pixso-vector-2_536 pixso-relative-no-shrink"
                                                                            ></div>
                                                                        </div>
                                                                    </div>
                                                                    <div className="stroke-2_529"></div>
                                                                </div>
                                                            </div>
                                                        </div>
                                                        <div
                                                            id="2_538"
                                                            className="Pixso-frame-2_538 pixso-relative-flex"
                                                        >
                                                            <div className="frame-content-2_538 pixso-relative-flex">
                                                                <p
                                                                    id="2_539"
                                                                    className="Pixso-paragraph-2_539 pixso-relative-no-shrink pixso-h-auto"
                                                                >
                                                                    {"可见范围"}
                                                                </p>
                                                                <div
                                                                    id="2_540"
                                                                    className="stroke-wrapper-2_540 pixso-relative-no-shrink pixso-flex"
                                                                    {...pressable(cycleVisibility)}
                                                                >
                                                                    <div className="Pixso-frame-2_540 pixso-relative-no-shrink pixso-flex">
                                                                        <div className="frame-content-2_540 pixso-relative-flex">
                                                                            <div
                                                                                id="2_541"
                                                                                className="Pixso-frame-2_541 pixso-relative-no-shrink"
                                                                            >
                                                                                <div
                                                                                    id="2_542"
                                                                                    className="stroke-wrapper-2_542"
                                                                                >
                                                                                    <div className="Pixso-rectangle-2_542 pixso-position-relative"></div>
                                                                                    <div className="stroke-2_542"></div>
                                                                                </div>
                                                                                <div
                                                                                    id="2_543"
                                                                                    className="Pixso-vector-2_543"
                                                                                ></div>
                                                                            </div>
                                                                            <p
                                                                                id="2_544"
                                                                                className="Pixso-paragraph-2_544 pixso-position-relative pixso-h-auto"
                                                                            >
                                                                                {visibility}
                                                                            </p>
                                                                            <div
                                                                                id="2_545"
                                                                                className="Pixso-vector-2_545 pixso-relative-no-shrink"
                                                                            ></div>
                                                                        </div>
                                                                    </div>
                                                                    <div className="stroke-2_540"></div>
                                                                </div>
                                                            </div>
                                                        </div>
                                                    </div>
                                                </div>
                                                <div
                                                    id="2_547"
                                                    className="Pixso-frame-2_547 pixso-relative-no-shrink pixso-flex"
                                                >
                                                    <div className="frame-content-2_547 pixso-relative-flex">
                                                        <div
                                                            id="2_548"
                                                            className="stroke-wrapper-2_548 pixso-relative-no-shrink pixso-flex"
                                                            {...pressable(() => void updateSetting("autoSync"))}
                                                        >
                                                            <div className="Pixso-frame-2_548 pixso-relative-no-shrink pixso-flex">
                                                                <div className="frame-content-2_548 pixso-relative-flex">
                                                                    <div
                                                                        id="2_549"
                                                                        className="Pixso-frame-2_549 pixso-relative-flex"
                                                                    >
                                                                        <div className="frame-content-2_549 pixso-relative-flex">
                                                                            <p
                                                                                id="2_550"
                                                                                className="Pixso-paragraph-2_550 pixso-relative-no-shrink pixso-h-auto"
                                                                            >
                                                                                {
                                                                                    "自动增量同步云盘"
                                                                                }
                                                                            </p>
                                                                            <p
                                                                                id="2_551"
                                                                                className="Pixso-paragraph-2_551 pixso-relative-no-shrink pixso-h-auto"
                                                                            >
                                                                                {
                                                                                    "每周一 08:00 同步钉钉文档与飞书云盘"
                                                                                }
                                                                            </p>
                                                                        </div>
                                                                    </div>
                                                                    <div
                                                                        id="2_552"
                                                                        className={`vector-wrapper-2_552 pixso-relative-no-shrink pixso-flex${autoSync ? "" : " hc-toggle-off"}`}
                                                                    >
                                                                        <div
                                                                            id="2_552"
                                                                            className="Pixso-vector-2_552"
                                                                        ></div>
                                                                    </div>
                                                                </div>
                                                            </div>
                                                            <div className="stroke-2_548"></div>
                                                        </div>
                                                        <div
                                                            id="2_554"
                                                            className="stroke-wrapper-2_554 pixso-relative-no-shrink pixso-flex"
                                                            {...pressable(() => void updateSetting("deepSearch"))}
                                                        >
                                                            <div className="Pixso-frame-2_554 pixso-relative-no-shrink pixso-flex">
                                                                <div className="frame-content-2_554 pixso-relative-flex">
                                                                    <div
                                                                        id="2_555"
                                                                        className="Pixso-frame-2_555 pixso-relative-flex"
                                                                    >
                                                                        <div className="frame-content-2_555 pixso-relative-flex">
                                                                            <p
                                                                                id="2_556"
                                                                                className="Pixso-paragraph-2_556 pixso-relative-no-shrink pixso-h-auto"
                                                                            >
                                                                                {
                                                                                    "启用深度思考检索"
                                                                                }
                                                                            </p>
                                                                            <p
                                                                                id="2_557"
                                                                                className="Pixso-paragraph-2_557 pixso-relative-no-shrink pixso-h-auto"
                                                                            >
                                                                                {
                                                                                    "回答前进行多步推理并生成 wiki 结论卡片"
                                                                                }
                                                                            </p>
                                                                        </div>
                                                                    </div>
                                                                    <div
                                                                        id="2_558"
                                                                        className={`vector-wrapper-2_558 pixso-relative-no-shrink pixso-flex${deepSearch ? "" : " hc-toggle-off"}`}
                                                                    >
                                                                        <div
                                                                            id="2_558"
                                                                            className="Pixso-vector-2_558"
                                                                        ></div>
                                                                    </div>
                                                                </div>
                                                            </div>
                                                            <div className="stroke-2_554"></div>
                                                        </div>
                                                        <div
                                                            id="2_560"
                                                            className="stroke-wrapper-2_560 pixso-relative-no-shrink pixso-flex"
                                                            {...pressable(() => void updateSetting("citations"))}
                                                        >
                                                            <div className="Pixso-frame-2_560 pixso-relative-no-shrink pixso-flex">
                                                                <div className="frame-content-2_560 pixso-relative-flex">
                                                                    <div
                                                                        id="2_561"
                                                                        className="Pixso-frame-2_561 pixso-relative-flex"
                                                                    >
                                                                        <div className="frame-content-2_561 pixso-relative-flex">
                                                                            <p
                                                                                id="2_562"
                                                                                className="Pixso-paragraph-2_562 pixso-relative-no-shrink pixso-h-auto"
                                                                            >
                                                                                {
                                                                                    "生成引用来源"
                                                                                }
                                                                            </p>
                                                                            <p
                                                                                id="2_563"
                                                                                className="Pixso-paragraph-2_563 pixso-relative-no-shrink pixso-h-auto"
                                                                            >
                                                                                {
                                                                                    "回答中展示原文片段与页码定位"
                                                                                }
                                                                            </p>
                                                                        </div>
                                                                    </div>
                                                                    <div
                                                                        id="2_564"
                                                                        className={`vector-wrapper-2_564 pixso-relative-no-shrink pixso-flex${citations ? "" : " hc-toggle-off"}`}
                                                                    >
                                                                        <div
                                                                            id="2_564"
                                                                            className="Pixso-vector-2_564"
                                                                        ></div>
                                                                    </div>
                                                                </div>
                                                            </div>
                                                            <div className="stroke-2_560"></div>
                                                        </div>
                                                    </div>
                                                </div>
                                                <div
                                                    id="2_566"
                                                    className="Pixso-frame-2_566 pixso-relative-no-shrink pixso-flex"
                                                >
                                                    <div className="frame-content-2_566 pixso-relative-flex">
                                                        <div
                                                            id="2_567"
                                                            className="Pixso-frame-2_567 pixso-relative-no-shrink pixso-flex"
                                                        >
                                                            <div className="frame-content-2_567 pixso-relative-flex">
                                                                <div
                                                                    id="2_568"
                                                                    className="Pixso-vector-2_568 pixso-relative-no-shrink"
                                                                ></div>
                                                                <p
                                                                    id="2_571"
                                                                    className="Pixso-paragraph-2_571 pixso-relative-auto-size pixso-flex-shrink-0"
                                                                >
                                                                    {
                                                                        "数据在企业内网加密存储"
                                                                    }
                                                                </p>
                                                            </div>
                                                        </div>
                                                        <div
                                                            id="2_572"
                                                            className="Pixso-frame-2_572 pixso-relative-no-shrink pixso-flex"
                                                        >
                                                            <div className="frame-content-2_572 pixso-relative-flex">
                                                                <div
                                                                    id="2_573"
                                                                    className="stroke-wrapper-2_573 pixso-relative-no-shrink pixso-flex"
                                                                    {...pressable(() => {
                                                                        notify("已取消创建项目");
                                                                        navigate("/frame2688");
                                                                    })}
                                                                >
                                                                    <div className="Pixso-frame-2_573 pixso-relative-no-shrink pixso-flex">
                                                                        <div className="frame-content-2_573 pixso-relative-flex">
                                                                            <p
                                                                                id="2_574"
                                                                                className="Pixso-paragraph-2_574 pixso-relative-auto-size pixso-flex-shrink-0"
                                                                            >
                                                                                {
                                                                                    "取消"
                                                                                }
                                                                            </p>
                                                                        </div>
                                                                    </div>
                                                                    <div className="stroke-2_573"></div>
                                                                </div>
                                                                <div
                                                                    id="2_575"
                                                                    className="Pixso-frame-2_575 pixso-relative-no-shrink pixso-flex"
                                                                    {...pressable(() => void handleCreate())}
                                                                >
                                                                    <div className="frame-content-2_575 pixso-relative-flex">
                                                                        <p
                                                                            id="2_576"
                                                                            className="Pixso-paragraph-2_576 pixso-relative-auto-size pixso-flex-shrink-0"
                                                                        >
                                                                            {
                                                                                "创建项目并上传资料"
                                                                            }
                                                                        </p>
                                                                        <div
                                                                            id="2_577"
                                                                            className="Pixso-vector-2_577 pixso-relative-no-shrink"
                                                                        ></div>
                                                                    </div>
                                                                </div>
                                                            </div>
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                        <div className="stroke-2_448"></div>
                                    </div>
                                    <div
                                        id="2_580"
                                        className="Pixso-frame-2_580 pixso-relative-no-shrink pixso-flex"
                                    >
                                        <div className="frame-content-2_580 pixso-relative-flex">
                                            <div
                                                id="2_581"
                                                className="Pixso-frame-2_581 pixso-relative-no-shrink pixso-flex"
                                            >
                                                <div className="frame-content-2_581 pixso-relative-flex">
                                                    <div
                                                        id="2_582"
                                                        className="Pixso-frame-2_582 pixso-relative-no-shrink pixso-flex"
                                                    >
                                                        <div className="frame-content-2_582 pixso-relative-flex">
                                                            <div
                                                                id="2_583"
                                                                className="Pixso-frame-2_583 pixso-relative-no-shrink pixso-flex"
                                                            >
                                                                <div className="frame-content-2_583 pixso-relative-flex">
                                                                    <div
                                                                        id="2_584"
                                                                        className="Pixso-vector-2_584 pixso-relative-no-shrink"
                                                                    ></div>
                                                                </div>
                                                            </div>
                                                            <p
                                                                id="2_589"
                                                                className="Pixso-paragraph-2_589 pixso-position-relative pixso-h-auto"
                                                            >
                                                                {
                                                                    "HyperCortex 建议"
                                                                }
                                                            </p>
                                                            <div
                                                                id="2_590"
                                                                className="Pixso-frame-2_590 pixso-relative-no-shrink pixso-flex"
                                                            >
                                                                <div className="frame-content-2_590 pixso-relative-flex">
                                                                    <p
                                                                        id="2_591"
                                                                        className="Pixso-paragraph-2_591 pixso-relative-auto-size pixso-flex-shrink-0"
                                                                    >
                                                                        {"AI"}
                                                                    </p>
                                                                </div>
                                                            </div>
                                                        </div>
                                                    </div>
                                                    <p
                                                        id="2_592"
                                                        className="Pixso-paragraph-2_592 pixso-relative-no-shrink pixso-h-auto"
                                                    >
                                                        {
                                                            "检测到 4 个命名相近的历史项目，建议复用「产品知识中枢」的切片策略。"
                                                        }
                                                    </p>
                                                    <div
                                                        id="2_593"
                                                        className="stroke-wrapper-2_593 pixso-relative-no-shrink pixso-flex"
                                                    >
                                                        <div className="Pixso-frame-2_593 pixso-relative-no-shrink pixso-flex">
                                                            <div className="frame-content-2_593 pixso-relative-flex">
                                                                <div
                                                                    id="2_594"
                                                                    className="Pixso-frame-2_594 pixso-relative-no-shrink pixso-flex"
                                                                    {...pressable(applyRecommended)}
                                                                >
                                                                    <div className="frame-content-2_594 pixso-relative-flex">
                                                                        <p
                                                                            id="2_595"
                                                                            className="Pixso-paragraph-2_595 pixso-relative-auto-size pixso-flex-shrink-0"
                                                                        >
                                                                            {
                                                                                "推荐配置"
                                                                            }
                                                                        </p>
                                                                        <p
                                                                            id="2_596"
                                                                            className="Pixso-paragraph-2_596 pixso-relative-auto-size pixso-flex-shrink-0"
                                                                        >
                                                                            {
                                                                                "一键应用"
                                                                            }
                                                                        </p>
                                                                    </div>
                                                                </div>
                                                                <div
                                                                    id="2_597"
                                                                    className="Pixso-frame-2_597 pixso-relative-no-shrink pixso-flex"
                                                                >
                                                                    <div className="frame-content-2_597 pixso-relative-flex">
                                                                        <div
                                                                            id="2_598"
                                                                            className="Pixso-frame-2_598 pixso-relative-no-shrink pixso-flex"
                                                                        >
                                                                            <div className="frame-content-2_598 pixso-relative-flex">
                                                                                <p
                                                                                    id="2_599"
                                                                                    className="Pixso-paragraph-2_599 pixso-relative-auto-size pixso-flex-shrink-0"
                                                                                >
                                                                                    {
                                                                                        "语义切片 512"
                                                                                    }
                                                                                </p>
                                                                            </div>
                                                                        </div>
                                                                        <div
                                                                            id="2_600"
                                                                            className="Pixso-frame-2_600 pixso-relative-no-shrink pixso-flex"
                                                                        >
                                                                            <div className="frame-content-2_600 pixso-relative-flex">
                                                                                <p
                                                                                    id="2_601"
                                                                                    className="Pixso-paragraph-2_601 pixso-relative-auto-size pixso-flex-shrink-0"
                                                                                >
                                                                                    {
                                                                                        "混合检索"
                                                                                    }
                                                                                </p>
                                                                            </div>
                                                                        </div>
                                                                        <div
                                                                            id="2_602"
                                                                            className="Pixso-frame-2_602 pixso-relative-no-shrink pixso-flex"
                                                                        >
                                                                            <div className="frame-content-2_602 pixso-relative-flex">
                                                                                <p
                                                                                    id="2_603"
                                                                                    className="Pixso-paragraph-2_603 pixso-relative-auto-size pixso-flex-shrink-0"
                                                                                >
                                                                                    {
                                                                                        "引用溯源开启"
                                                                                    }
                                                                                </p>
                                                                            </div>
                                                                        </div>
                                                                    </div>
                                                                </div>
                                                            </div>
                                                        </div>
                                                        <div className="stroke-2_593"></div>
                                                    </div>
                                                </div>
                                            </div>
                                            <div
                                                id="2_604"
                                                className="stroke-wrapper-2_604 pixso-relative-no-shrink pixso-flex"
                                            >
                                                <div className="Pixso-frame-2_604 pixso-relative-no-shrink pixso-flex">
                                                    <div className="frame-content-2_604 pixso-relative-flex">
                                                        <div
                                                            id="2_605"
                                                            className="Pixso-frame-2_605 pixso-relative-no-shrink pixso-flex"
                                                        >
                                                            <div className="frame-content-2_605 pixso-relative-flex">
                                                                <p
                                                                    id="2_606"
                                                                    className="Pixso-paragraph-2_606 pixso-relative-auto-size pixso-flex-shrink-0"
                                                                >
                                                                    {"最近打开"}
                                                                </p>
                                                                <p
                                                                    id="2_607"
                                                                    className="Pixso-paragraph-2_607 pixso-relative-auto-size pixso-flex-shrink-0"
                                                                >
                                                                    {"全部"}
                                                                </p>
                                                            </div>
                                                        </div>
                                                        <div
                                                            id="2_608"
                                                            className="Pixso-frame-2_608 pixso-relative-no-shrink pixso-flex"
                                                        >
                                                            <div className="frame-content-2_608 pixso-relative-flex">
                                                                <div
                                                                    id="2_609"
                                                                    className="Pixso-frame-2_609 pixso-relative-no-shrink pixso-flex"
                                                                >
                                                                    <div className="frame-content-2_609 pixso-relative-flex">
                                                                        <div
                                                                            id="2_610"
                                                                            className="Pixso-rectangle-2_610 pixso-relative-no-shrink"
                                                                        ></div>
                                                                        <p
                                                                            id="2_611"
                                                                            className="Pixso-paragraph-2_611 pixso-position-relative pixso-h-auto"
                                                                        >
                                                                            {
                                                                                "2025 Q3 产品路线图访谈"
                                                                            }
                                                                        </p>
                                                                        <div
                                                                            id="2_612"
                                                                            className="Pixso-frame-2_612 pixso-relative-no-shrink pixso-flex"
                                                                        >
                                                                            <div className="frame-content-2_612 pixso-relative-flex">
                                                                                <div
                                                                                    id="2_613"
                                                                                    className="Pixso-vector-2_613 pixso-relative-no-shrink"
                                                                                ></div>
                                                                                <p
                                                                                    id="2_616"
                                                                                    className="Pixso-paragraph-2_616 pixso-relative-auto-size pixso-flex-shrink-0"
                                                                                >
                                                                                    {
                                                                                        "已索引"
                                                                                    }
                                                                                </p>
                                                                            </div>
                                                                        </div>
                                                                    </div>
                                                                </div>
                                                                <div
                                                                    id="2_617"
                                                                    className="Pixso-frame-2_617 pixso-relative-no-shrink pixso-flex"
                                                                >
                                                                    <div className="frame-content-2_617 pixso-relative-flex">
                                                                        <p
                                                                            id="2_618"
                                                                            className="Pixso-paragraph-2_618 pixso-position-relative pixso-h-auto"
                                                                        >
                                                                            {
                                                                                "产品知识中枢"
                                                                            }
                                                                        </p>
                                                                        <p
                                                                            id="2_619"
                                                                            className="Pixso-paragraph-2_619 pixso-relative-auto-size pixso-flex-shrink-0"
                                                                        >
                                                                            {
                                                                                "24 份资料"
                                                                            }
                                                                        </p>
                                                                        <p
                                                                            id="2_620"
                                                                            className="Pixso-paragraph-2_620 pixso-relative-auto-size pixso-flex-shrink-0"
                                                                        >
                                                                            {
                                                                                "·"
                                                                            }
                                                                        </p>
                                                                        <p
                                                                            id="2_621"
                                                                            className="Pixso-paragraph-2_621 pixso-relative-auto-size pixso-flex-shrink-0"
                                                                        >
                                                                            {
                                                                                "今天 10:24"
                                                                            }
                                                                        </p>
                                                                    </div>
                                                                </div>
                                                            </div>
                                                        </div>
                                                        <div
                                                            id="2_622"
                                                            className="Pixso-frame-2_622 pixso-relative-no-shrink pixso-flex"
                                                        >
                                                            <div className="frame-content-2_622 pixso-relative-flex">
                                                                <div
                                                                    id="2_623"
                                                                    className="Pixso-frame-2_623 pixso-relative-no-shrink pixso-flex"
                                                                >
                                                                    <div className="frame-content-2_623 pixso-relative-flex">
                                                                        <div
                                                                            id="2_624"
                                                                            className="Pixso-rectangle-2_624 pixso-relative-no-shrink"
                                                                        ></div>
                                                                        <p
                                                                            id="2_625"
                                                                            className="Pixso-paragraph-2_625 pixso-position-relative pixso-h-auto"
                                                                        >
                                                                            {
                                                                                "欧盟临床数据合规 FAQs"
                                                                            }
                                                                        </p>
                                                                        <div
                                                                            id="2_626"
                                                                            className="Pixso-frame-2_626 pixso-relative-no-shrink pixso-flex"
                                                                        >
                                                                            <div className="frame-content-2_626 pixso-relative-flex">
                                                                                <div
                                                                                    id="2_627"
                                                                                    className="Pixso-vector-2_627 pixso-relative-no-shrink"
                                                                                ></div>
                                                                                <p
                                                                                    id="2_629"
                                                                                    className="Pixso-paragraph-2_629 pixso-relative-auto-size pixso-flex-shrink-0"
                                                                                >
                                                                                    {
                                                                                        "解析中"
                                                                                    }
                                                                                </p>
                                                                            </div>
                                                                        </div>
                                                                    </div>
                                                                </div>
                                                                <div
                                                                    id="2_630"
                                                                    className="Pixso-frame-2_630 pixso-relative-no-shrink pixso-flex"
                                                                >
                                                                    <div className="frame-content-2_630 pixso-relative-flex">
                                                                        <p
                                                                            id="2_631"
                                                                            className="Pixso-paragraph-2_631 pixso-position-relative pixso-h-auto"
                                                                        >
                                                                            {
                                                                                "临床研究资料库"
                                                                            }
                                                                        </p>
                                                                        <p
                                                                            id="2_632"
                                                                            className="Pixso-paragraph-2_632 pixso-relative-auto-size pixso-flex-shrink-0"
                                                                        >
                                                                            {
                                                                                "18 份资料"
                                                                            }
                                                                        </p>
                                                                        <p
                                                                            id="2_633"
                                                                            className="Pixso-paragraph-2_633 pixso-relative-auto-size pixso-flex-shrink-0"
                                                                        >
                                                                            {
                                                                                "·"
                                                                            }
                                                                        </p>
                                                                        <p
                                                                            id="2_634"
                                                                            className="Pixso-paragraph-2_634 pixso-relative-auto-size pixso-flex-shrink-0"
                                                                        >
                                                                            {
                                                                                "昨天 17:02"
                                                                            }
                                                                        </p>
                                                                    </div>
                                                                </div>
                                                            </div>
                                                        </div>
                                                        <div
                                                            id="2_635"
                                                            className="Pixso-frame-2_635 pixso-relative-no-shrink pixso-flex"
                                                        >
                                                            <div className="frame-content-2_635 pixso-relative-flex">
                                                                <div
                                                                    id="2_636"
                                                                    className="Pixso-frame-2_636 pixso-relative-no-shrink pixso-flex"
                                                                >
                                                                    <div className="frame-content-2_636 pixso-relative-flex">
                                                                        <div
                                                                            id="2_637"
                                                                            className="Pixso-rectangle-2_637 pixso-relative-no-shrink"
                                                                        ></div>
                                                                        <p
                                                                            id="2_638"
                                                                            className="Pixso-paragraph-2_638 pixso-position-relative pixso-h-auto"
                                                                        >
                                                                            {
                                                                                "供应链风险复盘档案"
                                                                            }
                                                                        </p>
                                                                        <div
                                                                            id="2_639"
                                                                            className="Pixso-frame-2_639 pixso-relative-no-shrink pixso-flex"
                                                                        >
                                                                            <div className="frame-content-2_639 pixso-relative-flex">
                                                                                <div
                                                                                    id="2_640"
                                                                                    className="Pixso-vector-2_640 pixso-relative-no-shrink"
                                                                                ></div>
                                                                                <p
                                                                                    id="2_643"
                                                                                    className="Pixso-paragraph-2_643 pixso-relative-auto-size pixso-flex-shrink-0"
                                                                                >
                                                                                    {
                                                                                        "已索引"
                                                                                    }
                                                                                </p>
                                                                            </div>
                                                                        </div>
                                                                    </div>
                                                                </div>
                                                                <div
                                                                    id="2_644"
                                                                    className="Pixso-frame-2_644 pixso-relative-no-shrink pixso-flex"
                                                                >
                                                                    <div className="frame-content-2_644 pixso-relative-flex">
                                                                        <p
                                                                            id="2_645"
                                                                            className="Pixso-paragraph-2_645 pixso-position-relative pixso-h-auto"
                                                                        >
                                                                            {
                                                                                "供应链运营手册"
                                                                            }
                                                                        </p>
                                                                        <p
                                                                            id="2_646"
                                                                            className="Pixso-paragraph-2_646 pixso-relative-auto-size pixso-flex-shrink-0"
                                                                        >
                                                                            {
                                                                                "31 份资料"
                                                                            }
                                                                        </p>
                                                                        <p
                                                                            id="2_647"
                                                                            className="Pixso-paragraph-2_647 pixso-relative-auto-size pixso-flex-shrink-0"
                                                                        >
                                                                            {
                                                                                "·"
                                                                            }
                                                                        </p>
                                                                        <p
                                                                            id="2_648"
                                                                            className="Pixso-paragraph-2_648 pixso-relative-auto-size pixso-flex-shrink-0"
                                                                        >
                                                                            {
                                                                                "9 月 28 日"
                                                                            }
                                                                        </p>
                                                                    </div>
                                                                </div>
                                                            </div>
                                                        </div>
                                                        <div
                                                            id="2_649"
                                                            className="stroke-wrapper-2_649 pixso-relative-no-shrink pixso-flex"
                                                        >
                                                            <div className="Pixso-frame-2_649 pixso-relative-no-shrink pixso-flex">
                                                                <div className="frame-content-2_649 pixso-relative-flex">
                                                                    <div
                                                                        id="2_650"
                                                                        className="Pixso-vector-2_650 pixso-relative-no-shrink"
                                                                    ></div>
                                                                    <p
                                                                        id="2_653"
                                                                        className="Pixso-paragraph-2_653 pixso-position-relative pixso-h-auto"
                                                                    >
                                                                        {
                                                                            "同步自 4 个数据源，最近更新 3 分钟前"
                                                                        }
                                                                    </p>
                                                                </div>
                                                            </div>
                                                            <div className="stroke-2_649"></div>
                                                        </div>
                                                    </div>
                                                </div>
                                                <div className="stroke-2_604"></div>
                                            </div>
                                            <div
                                                id="2_654"
                                                className="stroke-wrapper-2_654 pixso-relative-no-shrink pixso-flex"
                                            >
                                                <div className="Pixso-frame-2_654 pixso-relative-no-shrink pixso-flex">
                                                    <div className="frame-content-2_654 pixso-relative-flex">
                                                        <p
                                                            id="2_655"
                                                            className="Pixso-paragraph-2_655 pixso-relative-no-shrink pixso-h-auto"
                                                        >
                                                            {"创建后自动完成"}
                                                        </p>
                                                        <div
                                                            id="2_656"
                                                            className="Pixso-frame-2_656 pixso-relative-no-shrink pixso-flex"
                                                        >
                                                            <div className="frame-content-2_656 pixso-relative-flex">
                                                                <div
                                                                    id="2_657"
                                                                    className="Pixso-frame-2_657 pixso-relative-no-shrink pixso-flex"
                                                                >
                                                                    <div className="frame-content-2_657 pixso-relative-flex">
                                                                        <div
                                                                            id="2_658"
                                                                            className="Pixso-vector-2_658 pixso-relative-no-shrink"
                                                                        ></div>
                                                                    </div>
                                                                </div>
                                                                <div
                                                                    id="2_665"
                                                                    className="Pixso-frame-2_665 pixso-relative-flex"
                                                                >
                                                                    <div className="frame-content-2_665 pixso-relative-flex">
                                                                        <p
                                                                            id="2_666"
                                                                            className="Pixso-paragraph-2_666 pixso-relative-no-shrink pixso-h-auto"
                                                                        >
                                                                            {
                                                                                "格式解析"
                                                                            }
                                                                        </p>
                                                                        <p
                                                                            id="2_667"
                                                                            className="Pixso-paragraph-2_667 pixso-relative-no-shrink pixso-h-auto"
                                                                        >
                                                                            {
                                                                                "PDF / DOCX / PPTX / 网页"
                                                                            }
                                                                        </p>
                                                                    </div>
                                                                </div>
                                                            </div>
                                                        </div>
                                                        <div
                                                            id="2_668"
                                                            className="Pixso-frame-2_668 pixso-relative-no-shrink pixso-flex"
                                                        >
                                                            <div className="frame-content-2_668 pixso-relative-flex">
                                                                <div
                                                                    id="2_669"
                                                                    className="Pixso-frame-2_669 pixso-relative-no-shrink pixso-flex"
                                                                >
                                                                    <div className="frame-content-2_669 pixso-relative-flex">
                                                                        <div
                                                                            id="2_670"
                                                                            className="Pixso-vector-2_670 pixso-relative-no-shrink"
                                                                        ></div>
                                                                    </div>
                                                                </div>
                                                                <div
                                                                    id="2_676"
                                                                    className="Pixso-frame-2_676 pixso-relative-flex"
                                                                >
                                                                    <div className="frame-content-2_676 pixso-relative-flex">
                                                                        <p
                                                                            id="2_677"
                                                                            className="Pixso-paragraph-2_677 pixso-relative-no-shrink pixso-h-auto"
                                                                        >
                                                                            {
                                                                                "智能切片"
                                                                            }
                                                                        </p>
                                                                        <p
                                                                            id="2_678"
                                                                            className="Pixso-paragraph-2_678 pixso-relative-no-shrink pixso-h-auto"
                                                                        >
                                                                            {
                                                                                "按语义段落保留上下文"
                                                                            }
                                                                        </p>
                                                                    </div>
                                                                </div>
                                                            </div>
                                                        </div>
                                                        <div
                                                            id="2_679"
                                                            className="Pixso-frame-2_679 pixso-relative-no-shrink pixso-flex"
                                                        >
                                                            <div className="frame-content-2_679 pixso-relative-flex">
                                                                <div
                                                                    id="2_680"
                                                                    className="Pixso-frame-2_680 pixso-relative-no-shrink pixso-flex"
                                                                >
                                                                    <div className="frame-content-2_680 pixso-relative-flex">
                                                                        <div
                                                                            id="2_681"
                                                                            className="Pixso-vector-2_681 pixso-relative-no-shrink"
                                                                        ></div>
                                                                    </div>
                                                                </div>
                                                                <div
                                                                    id="2_685"
                                                                    className="Pixso-frame-2_685 pixso-relative-flex"
                                                                >
                                                                    <div className="frame-content-2_685 pixso-relative-flex">
                                                                        <p
                                                                            id="2_686"
                                                                            className="Pixso-paragraph-2_686 pixso-relative-no-shrink pixso-h-auto"
                                                                        >
                                                                            {
                                                                                "向量索引"
                                                                            }
                                                                        </p>
                                                                        <p
                                                                            id="2_687"
                                                                            className="Pixso-paragraph-2_687 pixso-relative-no-shrink pixso-h-auto"
                                                                        >
                                                                            {
                                                                                "混合检索 · 平均 18 秒"
                                                                            }
                                                                        </p>
                                                                    </div>
                                                                </div>
                                                            </div>
                                                        </div>
                                                    </div>
                                                </div>
                                                <div className="stroke-2_654"></div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};
export default Frame2319;
