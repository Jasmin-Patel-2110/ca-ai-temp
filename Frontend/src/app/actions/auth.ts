"use server";

import { cookies } from "next/headers";
import { UserProfile } from "@/types";
import { LoginSchema, RegisterSchema } from "@/lib/schemas";
import apiService from "@/lib/apiService";
import { decodeJWT } from "@/lib/utils";
import { LoginApiResponse, RegisterApiResponse, ApiErrorResponse, UpdateUserPayload, UpdateUserResponse } from "@/types/authenticationTypes";

export async function loginAction(formData: FormData) {

  const validatedFields = LoginSchema.safeParse(Object.fromEntries(formData.entries()));

  if (!validatedFields.success) {
    return { success: false, error: "Invalid fields" };
  }

  const { email, password } = validatedFields.data;

  try {
    const responseData = await apiService.post<LoginApiResponse>(
      "/auth/login",
      {
        email: email,
        password: password,
      },
      { useToken: false }
    );
    const token = responseData?.token;

    if (!token) {
      return { success: false, error: "Login failed: No access token provided by server." };
    }

    // Decode JWT payload to extract user details embedded in the token
    let user: UserProfile = { name: "", email, company: "", role: "User" };
    const decoded = decodeJWT(token);
    if (decoded) {
      user = {
        sub: decoded?.sub || decoded?.id || decoded?.user_id || decoded?.userId || "",
        name: decoded?.name || decoded?.username || email.split("@")[0],
        email: decoded?.email || email,
        company: decoded?.company || decoded?.company_name || "",
        role: decoded?.role || "User",
        gstNumber: decoded?.gst_number || "",
        mobileNumber: decoded?.mobile_number || decoded?.phone || "",
        address: decoded?.address || ""
      };
    }

    const cookieStore = await cookies();
    cookieStore.set("token", token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      maxAge: 60 * 60 * 12, // 12 hours
      path: "/",
    });

    return { success: true, user, token };
  } catch (error: unknown) {
    const apiError = error as ApiErrorResponse;
    const detail = apiError.response?.data?.detail;
    const errorMessage = apiError.response?.data?.message ||
      (typeof detail === "string" ? detail : (Array.isArray(detail) ? detail[0]?.msg : undefined)) ||
      "Invalid email or password";
    return { success: false, error: errorMessage };
  }
}

export async function logoutAction() {
  const cookieStore = await cookies();
  cookieStore.set("token", "", { expires: new Date(0) });
  return { success: true };
}

export async function registerAction(formData: FormData) {
  const validatedFields = RegisterSchema.safeParse(Object.fromEntries(formData.entries()));

  if (!validatedFields.success) {
    return { success: false, error: "Invalid fields" };
  }

  const { name, email, companyName, password } = validatedFields.data;

  try {
    const responseData = await apiService.post<RegisterApiResponse>(
      "/auth/register",
      {
        name: name,
        company_name: companyName,
        email: email,
        password: password
      },
      { useToken: false }
    );

    return {
      success: true,
      message: responseData?.message || "Registered Success",
      data: responseData?.data
    };
  } catch (error: unknown) {
    const apiError = error as ApiErrorResponse;
    const detail = apiError.response?.data?.detail;
    const errorMessage = apiError.response?.data?.message ||
      (typeof detail === "string" ? detail : (Array.isArray(detail) ? detail[0]?.msg : undefined)) ||
      "Registration failed";
    return { success: false, error: errorMessage };
  }
}

export async function updateUserAction(userId: string | number, data: Partial<UserProfile>) {
  try {
    const cookieStore = await cookies();
    const token = cookieStore.get("token")?.value;

    if (!token) {
      return { success: false, error: "Not authenticated" };
    }

    // Map frontend fields to backend expected fields as requested
    const payload: UpdateUserPayload = {};
    if (data.name !== undefined) payload.name = data.name;
    if (data.email !== undefined) payload.email = data.email;
    if (data.company !== undefined) payload.company_name = data.company;
    if (data.gstNumber !== undefined) payload.gst_number = data.gstNumber;
    if (data.address !== undefined) payload.address = data.address;
    if (data.mobileNumber !== undefined) payload.mobile_number = data.mobileNumber;

    const response = await apiService.patch<UpdateUserResponse>(`/users/${userId}`, payload, {
      headers: {
        "Authorization": `Bearer ${token}`
      }
    });

    return { success: true, data: response };
  } catch (error: unknown) {
    const apiError = error as ApiErrorResponse;
    const detail = apiError.response?.data?.detail;
    const errorMsg = (typeof detail === "string" ? detail : (Array.isArray(detail) ? detail[0]?.msg : undefined)) ||
      apiError.message ||
      "Failed to update user profile";
    return { success: false, error: errorMsg };
  }
}
