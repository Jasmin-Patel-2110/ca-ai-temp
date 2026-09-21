
import axios, { AxiosInstance, AxiosRequestConfig, AxiosResponse } from "axios";

// Encryption function (dummy implementation)
const encryptData = (data: unknown): string => {
    // Replace with your actual encryption logic
    return JSON.stringify(data);
};

// Decryption function (dummy implementation)
const decryptData = (data: string): unknown => {
    // Replace with your actual decryption logic
    return JSON.parse(data);
};

interface ApiServiceConfig {
    baseURL: string;
    timeout?: number;
    defaultToken?: string;
}

interface RequestConfig extends AxiosRequestConfig {
    useToken?: boolean;
    encrypt?: boolean;
    timeout?: number;
}

class ApiService {
    private axiosInstance: AxiosInstance;
    private defaultToken?: string;

    constructor(config: ApiServiceConfig) {
        this.axiosInstance = axios.create({
            baseURL: config.baseURL,
            timeout: config.timeout || 30000, // Default to 30 seconds
        });
        this.defaultToken = config.defaultToken;
        this.setupInterceptors();
    }

    private setupInterceptors() {
        this.axiosInstance.interceptors.request.use(
            (config: any) => {
                config.headers = config.headers || {};
                if (config.useToken && this.defaultToken) {
                    config.headers.Authorization = `Bearer ${this.defaultToken}`;
                }
                if (config.encrypt && config.data) {
                    config.data = encryptData(config.data);
                    config.headers["Content-Type"] = "text/plain";
                } else if (config.data instanceof FormData) {
                    config.headers["Content-Type"] = "multipart/form-data";
                }
                return config;
            },
            (error) => {
                return Promise.reject(error);
            }
        );

        this.axiosInstance.interceptors.response.use(
            (response: any) => {
                if (response.config.encrypt && typeof response.data === "string") {
                    response.data = decryptData(response.data);
                }
                return response;
            },
            (error) => {
                // If it's a timeout error from axios, we simply pass it through instead
                // of trying to use client-side toast modules which break in Server Actions.
                if (error.code === "ECONNABORTED") {
                    error.message = "The request took too long to respond.";
                }
                return Promise.reject(error);
            }
        );
    }

    private async request<T>(config: RequestConfig): Promise<T> {
        try {
            const response: AxiosResponse<T> = await this.axiosInstance.request(config);
            return response.data;
        } catch (error) {
            throw error;
        }
    }

    public get<T>(url: string, config?: RequestConfig): Promise<T> {
        return this.request<T>({ ...config, method: "GET", url, useToken: config?.useToken ?? true });
    }

    public post<T>(url: string, data: unknown, config?: RequestConfig): Promise<T> {
        return this.request<T>({ ...config, method: "POST", url, data, useToken: config?.useToken ?? true });
    }

    public put<T>(url: string, data: unknown, config?: RequestConfig): Promise<T> {
        return this.request<T>({ ...config, method: "PUT", url, data, useToken: config?.useToken ?? true });
    }

    public patch<T>(url: string, data: unknown, config?: RequestConfig): Promise<T> {
        return this.request<T>({ ...config, method: "PATCH", url, data, useToken: config?.useToken ?? true });
    }

    public delete<T>(url: string, config?: RequestConfig): Promise<T> {
        return this.request<T>({ ...config, method: "DELETE", url, useToken: config?.useToken ?? true });
    }

    public upload<T>(url: string, data: FormData, config?: RequestConfig): Promise<T> {
        return this.request<T>({ ...config, method: "POST", url, data, useToken: config?.useToken ?? true });
    }
}

const apiService = new ApiService({
    baseURL:
        typeof window === "undefined"
            ? process.env.API_URL || "http://127.0.0.1:8000"
            : process.env.NEXT_PUBLIC_API_URL || "",
});

export default apiService;
