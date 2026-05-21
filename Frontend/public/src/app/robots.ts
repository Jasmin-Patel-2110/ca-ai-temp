import { MetadataRoute } from "next";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: ["/dashboard/", "/settings/"],
    },
    sitemap: "https://ledger-ai-optimised.vercel.app/sitemap.xml",
  };
}
