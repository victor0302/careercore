import { renderHook, act, waitFor } from "@testing-library/react";
import { useAuth } from "@/hooks/useAuth";
import * as authLib from "@/lib/auth";
import * as apiLib from "@/lib/api";

jest.mock("@/lib/api", () => ({
  api: {
    get: jest.fn(),
    post: jest.fn(),
    patch: jest.fn(),
    delete: jest.fn(),
  },
  ApiRequestError: class ApiRequestError extends Error {
    status: number;
    detail: string;
    constructor(status: number, detail: string) {
      super(`API error ${status}: ${detail}`);
      this.status = status;
      this.detail = detail;
    }
  },
}));

jest.mock("@/lib/auth", () => ({
  getAccessToken: jest.fn(),
  setAccessToken: jest.fn(),
  clearTokens: jest.fn(),
  refreshAccessToken: jest.fn(),
}));

const mockApi = apiLib.api as jest.Mocked<typeof apiLib.api>;
const mockGetAccessToken = authLib.getAccessToken as jest.Mock;
const mockSetAccessToken = authLib.setAccessToken as jest.Mock;
const mockClearTokens = authLib.clearTokens as jest.Mock;

const fakeUser = {
  id: "user-1",
  email: "test@example.com",
  is_active: true,
  tier: "free" as const,
};

beforeEach(() => {
  jest.clearAllMocks();
});

describe("useAuth", () => {
  test("on mount with valid token: calls GET /auth/me and sets isAuthenticated: true", async () => {
    mockGetAccessToken.mockReturnValue("valid-token");
    mockApi.get.mockResolvedValue(fakeUser);

    const { result } = renderHook(() => useAuth());

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(mockApi.get).toHaveBeenCalledWith("/api/v1/auth/me");
    expect(result.current.isAuthenticated).toBe(true);
    expect(result.current.user).toEqual(fakeUser);
  });

  test("on mount with no token: skips /auth/me call, sets isAuthenticated: false", async () => {
    mockGetAccessToken.mockReturnValue(null);

    const { result } = renderHook(() => useAuth());

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(mockApi.get).not.toHaveBeenCalled();
    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.user).toBeNull();
  });

  test("login() calls POST /auth/login, stores token, then calls GET /auth/me", async () => {
    mockGetAccessToken.mockReturnValue(null);
    mockApi.post.mockResolvedValue({ access_token: "new-token", token_type: "bearer" });
    mockApi.get.mockResolvedValue(fakeUser);

    const { result } = renderHook(() => useAuth());

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    await act(async () => {
      await result.current.login({ email: "test@example.com", password: "password" });
    });

    expect(mockApi.post).toHaveBeenCalledWith(
      "/api/v1/auth/login",
      { email: "test@example.com", password: "password" },
      { skipAuth: true }
    );
    expect(mockSetAccessToken).toHaveBeenCalledWith("new-token");
    expect(mockApi.get).toHaveBeenCalledWith("/api/v1/auth/me");
    expect(result.current.isAuthenticated).toBe(true);
    expect(result.current.user).toEqual(fakeUser);
  });

  test("logout() calls POST /auth/logout and sets isAuthenticated: false", async () => {
    mockGetAccessToken.mockReturnValue("valid-token");
    mockApi.get.mockResolvedValue(fakeUser);
    mockApi.post.mockResolvedValue(undefined);

    const { result } = renderHook(() => useAuth());

    await waitFor(() => {
      expect(result.current.isAuthenticated).toBe(true);
    });

    await act(async () => {
      await result.current.logout();
    });

    expect(mockApi.post).toHaveBeenCalledWith(
      "/api/v1/auth/logout",
      undefined,
      { skipAuth: false }
    );
    expect(mockClearTokens).toHaveBeenCalled();
    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.user).toBeNull();
  });
});
