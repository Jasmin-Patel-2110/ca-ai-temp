import { createSlice, PayloadAction } from "@reduxjs/toolkit";
import { UserProfile } from "@/types";
import { decodeJWT } from "@/lib/utils";

interface AuthState {
    user: UserProfile | null;
    token: string | null;
    isLoading: boolean;
    error: string | null;
}

// Rehydrate user from localStorage on app start
function loadUser(): UserProfile | null {
    if (typeof window === "undefined") return null;
    try {
        const raw = localStorage.getItem("auth_user");
        if (!raw) return null;
        const parsed: UserProfile = JSON.parse(raw);
        // If stored user is missing `sub`, try to derive it from stored token
        const token = localStorage.getItem("auth_token");
        if (parsed && !parsed.sub && token) {
            const decoded = decodeJWT(token);
            if (decoded) {
                parsed.sub = decoded?.sub || decoded?.id || decoded?.user_id || decoded?.userId || parsed.sub;
            }
        }
        return parsed;
    } catch {
        return null;
    }
}

const initialState: AuthState = {
    user: loadUser(),
    token: typeof window !== "undefined" ? localStorage.getItem("auth_token") : null,
    isLoading: false,
    error: null,
};

const authSlice = createSlice({
    name: "auth",
    initialState,
    reducers: {
        loginStart(state) {
            state.isLoading = true;
            state.error = null;
        },
        loginSuccess(state, action: PayloadAction<{ user: UserProfile; token: string }>) {
            state.isLoading = false;
            state.user = action.payload.user;
            state.token = action.payload.token;
            // Persist to localStorage so state survives page navigation
            if (typeof window !== "undefined") {
                localStorage.setItem("auth_user", JSON.stringify(action.payload.user));
                localStorage.setItem("auth_token", action.payload.token);
            }
        },
        loginFailure(state, action: PayloadAction<string>) {
            state.isLoading = false;
            state.error = action.payload;
        },
        updateProfile(state, action: PayloadAction<UserProfile>) {
            state.user = action.payload;
            if (typeof window !== "undefined") {
                localStorage.setItem("auth_user", JSON.stringify(action.payload));
            }
        },
        logout(state) {
            state.user = null;
            state.token = null;
            if (typeof window !== "undefined") {
                localStorage.removeItem("auth_user");
                localStorage.removeItem("auth_token");
            }
        },
    },
});

export const { loginStart, loginSuccess, loginFailure, logout, updateProfile } = authSlice.actions;
export default authSlice.reducer;
