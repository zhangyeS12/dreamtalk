import { afterEach, expect, test, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import type { CoreClient, WorldCover } from "@dreamtalk/api-client";
import { useWorldCovers } from "../useWorldCovers";
afterEach(() => { cleanup(); vi.restoreAllMocks(); });
function Probe({ client, ids }: { client: CoreClient; ids: string[] }) {
  const covers = useWorldCovers(client, undefined, true, ids);
  return <output>{Object.keys(covers.appearances).sort().join(",")}</output>;
}
test("the mobile shelf fetches artwork only for visible worlds and evicts departed URLs", async () => {
  const list = ["a","b","c","d"].map(id => ({ world_id:id, mode:"image", faces:{ front:{ display:{digest:id} } } } as WorldCover));
  const read = vi.fn<CoreClient["coverImage"]>().mockResolvedValue(new Blob(["synthetic"]));
  const url = vi.fn().mockReturnValueOnce("blob:synthetic-a").mockReturnValueOnce("blob:synthetic-b").mockReturnValueOnce("blob:synthetic-c");
  Object.defineProperty(URL, "createObjectURL", { configurable:true, value:url });
  const revoke = vi.fn(); Object.defineProperty(URL, "revokeObjectURL", { configurable:true, value:revoke });
  const metadata = vi.fn(async () => list);
  const client = { listWorldCovers:metadata, coverImage:read } as unknown as CoreClient;
  const view = render(<Probe client={client} ids={["a","b"]}/>);
  await waitFor(() => expect(screen.getByRole("status").textContent).toBe("a,b"));
  expect(read.mock.calls.map(call => call[0])).toEqual(["a","b"]);
  view.rerender(<Probe client={client} ids={["c"]}/>);
  await waitFor(() => expect(screen.getByRole("status").textContent).toBe("c"));
  expect(metadata).toHaveBeenCalledTimes(1);
  expect(read.mock.calls.map(call => call[0])).toEqual(["a","b","c"]);
  expect(revoke).toHaveBeenCalledWith("blob:synthetic-a"); expect(revoke).toHaveBeenCalledWith("blob:synthetic-b");
  view.unmount(); expect(revoke).toHaveBeenCalledWith("blob:synthetic-c");
});
