"use client";

import { useState, useEffect } from "react";
import {
  User, Mail, Building2,
  Hash, MapPin, Phone,
  Save, ShieldCheck, Loader2
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useSelector, useDispatch } from "react-redux";
import { RootState } from "@/lib/redux/store";
import { updateUserAction } from "@/app/actions/auth";
import { updateProfile } from "@/lib/redux/slices/authSlice";
import { useToast } from "@/hooks/use-toast";

export default function SettingsPage() {
  const { user, token } = useSelector((state: RootState) => state.auth);
  const toast = useToast();
  const dispatch = useDispatch();
  const [isUpdating, setIsUpdating] = useState(false);

  const [formData, setFormData] = useState({
    name: "",
    company: "",
    gstNumber: "",
    mobileNumber: "",
    address: "",
  });

  useEffect(() => {
    if (user) {
      setFormData({
        name: user.name || "",
        company: user.company || "",
        gstNumber: user.gstNumber || "",
        mobileNumber: user.mobileNumber || "",
        address: user.address || "",
      });
    }
  }, [user]);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { id, value } = e.target;
    // Map ID to form data key if they differ
    const key = id === "companyName" ? "company" : id;
    setFormData(prev => ({ ...prev, [key]: value }));
  };

  const handleSave = async () => {
    if (!user) return;

    // Detect changed fields
    const updatedFields: any = {};
    if (formData.name !== (user.name || "")) updatedFields.name = formData.name;
    if (formData.company !== (user.company || "")) updatedFields.company = formData.company;
    if (formData.gstNumber !== (user.gstNumber || "")) updatedFields.gstNumber = formData.gstNumber;
    if (formData.mobileNumber !== (user.mobileNumber || "")) updatedFields.mobileNumber = formData.mobileNumber;
    if (formData.address !== (user.address || "")) updatedFields.address = formData.address;

    if (Object.keys(updatedFields).length === 0) {
      toast.info({ message: "No changes detected." });
      return;
    }

    setIsUpdating(true);
    try {
      const result = await updateUserAction(user.sub || "1", updatedFields);
      if (result.success) {
        // Update local Redux state with new user info
        dispatch(updateProfile({ ...user, ...updatedFields }));
        toast.success({
          message: "Profile updated successfully!",
        });
      } else {
        toast.errorAlert({
          message: result.error || "Failed to update profile.",
        });
      }
    } catch (error) {
      toast.errorAlert({
        message: "An unexpected error occurred.",
      });
    } finally {
      setIsUpdating(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-8 animate-in fade-in duration-500 pb-12 py-8">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div className="flex items-center gap-3">
          <div className="p-3 bg-primary/10 rounded-2xl">
            <ShieldCheck className="w-8 h-8 text-primary" />
          </div>
          <div>
            <h2 className="text-3xl font-bold text-foreground tracking-tight">Account Settings</h2>
            <p className="text-muted-foreground mt-1">Update your professional identity and contact information.</p>
          </div>
        </div>
        <Button
          onClick={handleSave}
          disabled={isUpdating}
          className="gap-2 shadow-lg h-12 px-8 rounded-xl bg-primary hover:bg-primary/90 min-w-[160px]"
        >
          {isUpdating ? (
            <Loader2 className="w-5 h-5 animate-spin" />
          ) : (
            <Save className="w-5 h-5" />
          )}
          {isUpdating ? "Saving..." : "Save Changes"}
        </Button>
      </div>

      <div className="bg-card rounded-3xl border border-border p-8 shadow-sm space-y-10 group transition-all hover:shadow-md">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-8">
          {/* Name */}
          <div className="space-y-2.5">
            <div className="flex items-center gap-2">
              <User className="w-4 h-4 text-primary" />
              <Label className="text-sm font-bold text-foreground">Full Name</Label>
            </div>
            <Input
              id="name"
              value={formData.name}
              onChange={handleInputChange}
              className="h-12 bg-muted/20 border-border focus:bg-background focus:ring-2 focus:ring-primary/20 transition-all rounded-xl px-4"
              placeholder="Enter your full name"
            />
          </div>

          {/* Email */}
          <div className="space-y-2.5">
            <div className="flex items-center gap-2">
              <Mail className="w-4 h-4 text-muted-foreground" />
              <Label className="text-sm font-bold text-muted-foreground">Email Address</Label>
              <span className="text-[10px] bg-muted px-1.5 py-0.5 rounded text-muted-foreground uppercase">Read Only</span>
            </div>
            <Input
              defaultValue={user?.email || ""}
              readOnly
              className="h-12 bg-muted/10 border-border cursor-not-allowed opacity-60 rounded-xl px-4 font-medium"
            />
          </div>

          {/* Company Name */}
          <div className="space-y-2.5">
            <div className="flex items-center gap-2">
              <Building2 className="w-4 h-4 text-primary" />
              <Label className="text-sm font-bold text-foreground">Company Name</Label>
            </div>
            <Input
              id="company"
              value={formData.company}
              onChange={handleInputChange}
              className="h-12 bg-muted/20 border-border focus:bg-background focus:ring-2 focus:ring-primary/20 transition-all rounded-xl px-4"
              placeholder="Enter company name"
            />
          </div>

          {/* GST Number */}
          <div className="space-y-2.5">
            <div className="flex items-center gap-2">
              <Hash className="w-4 h-4 text-primary" />
              <Label className="text-sm font-bold text-foreground">GST Number</Label>
            </div>
            <Input
              id="gstNumber"
              value={formData.gstNumber}
              onChange={handleInputChange}
              placeholder="e.g. 27AAAAA0000A1Z5"
              className="h-12 bg-muted/20 border-border focus:bg-background focus:ring-2 focus:ring-primary/20 transition-all rounded-xl px-4 uppercase"
            />
          </div>

          {/* Mobile Number */}
          <div className="space-y-2.5">
            <div className="flex items-center gap-2">
              <Phone className="w-4 h-4 text-primary" />
              <Label className="text-sm font-bold text-foreground">Mobile Number</Label>
            </div>
            <Input
              id="mobileNumber"
              type="tel"
              value={formData.mobileNumber}
              onChange={handleInputChange}
              className="h-12 bg-muted/20 border-border focus:bg-background focus:ring-2 focus:ring-primary/20 transition-all rounded-xl px-4"
              placeholder="Enter mobile number"
            />
          </div>

          {/* Empty space for grid alignment or add another field */}
          <div className="hidden sm:block" />

          <div className="sm:col-span-2 space-y-2.5">
            <div className="flex items-center gap-2">
              <MapPin className="w-4 h-4 text-primary" />
              <Label className="text-sm font-bold text-foreground">Business Address</Label>
            </div>
            <textarea
              id="address"
              placeholder="Enter your complete business address"
              value={formData.address}
              onChange={handleInputChange}
              className="w-full min-h-[120px] rounded-2xl border border-border bg-muted/20 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:bg-background transition-all resize-none"
            />
          </div>
        </div>

        {/* <div className="pt-4 border-t border-border flex items-center justify-between">
          <p className="text-xs text-muted-foreground italic">
            * Changes to your email address require administrative approval.
          </p>
          <Button variant="ghost" size="sm" className="text-destructive hover:bg-destructive/5 font-semibold">
            Deactivate Account
          </Button>
        </div> */}
      </div>
    </div>
  );
}
