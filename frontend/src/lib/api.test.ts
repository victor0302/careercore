import { api, ApiRequestError } from "@/lib/api";
import * as authLib from "@/lib/auth";

jest.mock("@/lib/auth", () => ({
  getAccessToken: jest.fn(),
  setAccessToken: jest.fn(),
  clearTokens: jest.fn(),
  refreshAccessToken: jest.fn(),
}));

const mockGetAccessToken = authLib.getAccessToken as jest.Mock;
const mockRefreshAccessToken = authLib.refreshAccessToken as jest.Mock;
const mockClearTokens = authLib.clearTokens as jest.Mock;

function makeResponse(status: number, body?: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: jest.fn().mockResolvedValue(body),
  } as unknown as Response;
}

let mockFetch: jest.Mock;

beforeEach(() => {
  mockFetch = jest.fn();
  global.fetch = mockFetch;
  jest.clearAllMocks();
});

describe("api client", () => {
  test("api.get attaches Authorization header when token present", async () => {
    mockGetAccessToken.mockReturnValue("test-token");
    mockFetch.mockResolvedValue(makeResponse(200, { data: "ok" }));

    await api.get("/test");

    expect(mockFetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer test-token",
        }),
      })
    );
  });

  test("api.get omits Authorization header when skipAuth: true", async () => {
    mockGetAccessToken.mockReturnValue("test-token");
    mockFetch.mockResolvedValue(makeResponse(200, { data: "ok" }));

    await api.get("/test", { skipAuth: true });

    const headers = mockFetch.mock.calls[0][1].headers as Record<string, string>;
    expect(headers).not.toHaveProperty("Authorization");
  });

  test("on 401, calls refreshAccessToken, retries once, succeeds with new token", async () => {
    mockGetAccessToken.mockReturnValue("old-token");
    mockRefreshAccessToken.mockResolvedValue("new-token");
    mockFetch
      .mockResolvedValueOnce(makeResponse(401))
      .mockResolvedValueOnce(makeResponse(200, { data: "ok" }));

    const result = await api.get("/test");

    expect(mockRefreshAccessToken).toHaveBeenCalledTimes(1);
    expect(mockFetch).toHaveBeenCalledTimes(2);
    expect(result).toEqual({ data: "ok" });
  });

  test("on 401 where refresh also fails, throws ApiRequestError(401)", async () => {
    mockGetAccessToken.mockReturnValue("old-token");
    mockRefreshAccessToken.mockResolvedValue(null);
    mockFetch.mockResolvedValue(makeResponse(401));

    await expect(api.get("/test")).rejects.toBeInstanceOf(ApiRequestError);
    await expect(api.get("/test")).rejects.toMatchObject({ status: 401 });
    expect(mockClearTokens).toHaveBeenCalled();
    expect(mockFetch).toHaveBeenCalledTimes(2); // one per rejects check above
  });

  test("on non-OK response, throws ApiRequestError with status and detail from body", async () => {
    mockGetAccessToken.mockReturnValue(null);
    mockFetch.mockResolvedValue(makeResponse(404, { detail: "Not found" }));

    await expect(api.get("/test")).rejects.toMatchObject({
      status: 404,
      detail: "Not found",
    });
  });

  test("204 response returns undefined without parsing JSON", async () => {
    mockGetAccessToken.mockReturnValue("token");
    const mockJson = jest.fn();
    mockFetch.mockResolvedValue({
      ok: true,
      status: 204,
      json: mockJson,
    } as unknown as Response);

    const result = await api.get("/test");

    expect(result).toBeUndefined();
    expect(mockJson).not.toHaveBeenCalled();
  });
});
