import Frame2688 from "@/views/Frame2688";
import Frame21608 from "@/views/Frame21608";
import Frame2319 from "@/views/Frame2319";
import Frame21123 from "@/views/Frame21123";
import Frame21992 from "@/views/Frame21992";

export const routes = [{
          path: "/frame2688",
          component: Frame2688,
          guid: "2:688",
        },
{
          path: "/frame21608",
          component: Frame21608,
          guid: "2:1608",
        },
{
          path: "/",
          component: Frame2319,
          guid: "2:319",
        },
{
          path: "/frame21123",
          component: Frame21123,
          guid: "2:1123",
        },
{
          path: "/frame21992",
          component: Frame21992,
          guid: "2:1992",
        }];


export const guidPathMap = new Map(
  routes.map((item) => [item.guid, item.path])
);
export const pathGuidMap = new Map(
  routes.map((item) => [item.path, item.guid])
);

export const getPathByGuid = (guid: string) => {
  return guidPathMap.get(guid) || "";
};

export const getGuidByPath = (path: string) => {
  return pathGuidMap.get(path) || "";
};
