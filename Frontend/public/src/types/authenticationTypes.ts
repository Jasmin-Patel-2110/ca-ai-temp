export interface ApiErrorResponse {
    response: {
        data: {
            message: string;
            detail: string | { msg: string }[];
            [key: string]: unknown;
        };
        status: number;
    };
    message: string;
    code: string;
}

export interface LoginApiResponse {
    token: string;
}

export interface RegisterApiResponse {
    success: boolean;
    message: string;
    data: {
        name: string;
        companyName: string;
        email: string;
    };
};

export interface UpdateUserPayload {
    name?: string;
    email?: string;
    company_name?: string;
    gst_number?: string;
    address?: string;
    mobile_number?: string;
}

export interface UpdateUserResponse {
    id: string | number;
    name: string;
    email: string;
    company_name: string;
    gst_number?: string;
    address?: string;
    mobile_number?: string;
    role: string;
}