-- ============================================================================
-- Citidy — Production Supabase PostgreSQL Schema & Security Policies (RLS)
-- DATATHON 2026 | Smart City Civic Complaint Management Platform
-- ============================================================================

-- 1. PROFILES (Extends Supabase auth.users)
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    full_name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    role TEXT NOT NULL DEFAULT 'citizen' CHECK (role IN ('citizen', 'admin')),
    phone TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. COMPLAINTS TABLE
CREATE TABLE IF NOT EXISTS public.complaints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    complaint_number TEXT UNIQUE NOT NULL,
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    address TEXT,
    zone TEXT DEFAULT 'ZONE_01',
    priority TEXT DEFAULT 'Medium' CHECK (priority IN ('Low', 'Medium', 'High', 'Critical')),
    status TEXT DEFAULT 'Submitted' CHECK (status IN (
        'Submitted', 'Under Review', 'Verified', 'Assigned',
        'In Progress', 'On Hold', 'Resolved', 'Closed', 'Reopened', 'Rejected'
    )),
    progress_percentage INTEGER DEFAULT 0 CHECK (progress_percentage BETWEEN 0 AND 100),
    estimated_resolution_at TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ,
    resolved_by TEXT,
    resolution_notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. COMPLAINT ATTACHMENTS (Before, After, Progress Evidence)
CREATE TABLE IF NOT EXISTS public.complaint_attachments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    complaint_id UUID NOT NULL REFERENCES public.complaints(id) ON DELETE CASCADE,
    uploaded_by UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    attachment_type TEXT NOT NULL CHECK (attachment_type IN ('before', 'after', 'progress', 'other')),
    file_path TEXT NOT NULL,
    file_name TEXT,
    file_size INTEGER,
    mime_type TEXT,
    caption TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. COMPLAINT STATUS HISTORY (Audit Trail)
CREATE TABLE IF NOT EXISTS public.complaint_status_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    complaint_id UUID NOT NULL REFERENCES public.complaints(id) ON DELETE CASCADE,
    old_status TEXT,
    new_status TEXT NOT NULL,
    progress_percentage INTEGER NOT NULL,
    note TEXT,
    changed_by UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 5. COMPLAINT ASSIGNMENTS
CREATE TABLE IF NOT EXISTS public.complaint_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    complaint_id UUID NOT NULL REFERENCES public.complaints(id) ON DELETE CASCADE,
    department TEXT NOT NULL,
    assigned_to TEXT,
    assigned_by UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    assigned_at TIMESTAMPTZ DEFAULT NOW(),
    status TEXT DEFAULT 'Active'
);

-- 6. NOTIFICATIONS TABLE
CREATE TABLE IF NOT EXISTS public.notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recipient_user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    complaint_id UUID REFERENCES public.complaints(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    notification_type TEXT NOT NULL,
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 7. RESOLUTION ESTIMATE HISTORY
CREATE TABLE IF NOT EXISTS public.resolution_estimate_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    complaint_id UUID NOT NULL REFERENCES public.complaints(id) ON DELETE CASCADE,
    previous_estimate TIMESTAMPTZ,
    new_estimate TIMESTAMPTZ NOT NULL,
    reason TEXT NOT NULL,
    changed_by UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 8. NOTIFICATION PREFERENCES
CREATE TABLE IF NOT EXISTS public.notification_preferences (
    user_id UUID PRIMARY KEY REFERENCES public.profiles(id) ON DELETE CASCADE,
    in_app_enabled BOOLEAN DEFAULT TRUE,
    email_enabled BOOLEAN DEFAULT TRUE,
    push_enabled BOOLEAN DEFAULT FALSE,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 9. ADMINISTRATIVE AUDIT EVENTS
CREATE TABLE IF NOT EXISTS public.administrative_audit_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    admin_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    target_id TEXT,
    details TEXT,
    ip_address TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 10. CITIZEN RESOLUTION FEEDBACK
CREATE TABLE IF NOT EXISTS public.citizen_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    complaint_id UUID NOT NULL REFERENCES public.complaints(id) ON DELETE CASCADE,
    citizen_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    is_problem_resolved BOOLEAN DEFAULT TRUE,
    feedback_comment TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add internal_notes and cluster_id columns to complaints if missing
ALTER TABLE public.complaints ADD COLUMN IF NOT EXISTS internal_notes TEXT;
ALTER TABLE public.complaints ADD COLUMN IF NOT EXISTS cluster_id TEXT;

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_complaints_user ON public.complaints(user_id);
CREATE INDEX IF NOT EXISTS idx_complaints_status ON public.complaints(status);
CREATE INDEX IF NOT EXISTS idx_complaints_zone ON public.complaints(zone);
CREATE INDEX IF NOT EXISTS idx_attachments_complaint ON public.complaint_attachments(complaint_id);
CREATE INDEX IF NOT EXISTS idx_notifications_recipient ON public.notifications(recipient_user_id, is_read);
CREATE INDEX IF NOT EXISTS idx_audit_admin ON public.administrative_audit_events(admin_id, created_at);
CREATE INDEX IF NOT EXISTS idx_feedback_complaint ON public.citizen_feedback(complaint_id);

-- ============================================================================
-- ROW LEVEL SECURITY (RLS) POLICIES
-- ============================================================================

ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.complaints ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.complaint_attachments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.complaint_status_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.complaint_assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.resolution_estimate_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notification_preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.administrative_audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.citizen_feedback ENABLE ROW LEVEL SECURITY;

-- Helper function to check if current authenticated user is an administrator
CREATE OR REPLACE FUNCTION public.is_admin()
RETURNS BOOLEAN AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1 FROM public.profiles
        WHERE id = auth.uid() AND role = 'admin'
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Profiles Policies
CREATE POLICY "Public profiles are readable by authenticated users"
ON public.profiles FOR SELECT
USING (auth.uid() IS NOT NULL);

CREATE POLICY "Users can insert their own initial profile"
ON public.profiles FOR INSERT
WITH CHECK (auth.uid() = id);

CREATE POLICY "Users can update their own profile name/phone, but cannot change their role"
ON public.profiles FOR UPDATE
USING (auth.uid() = id)
WITH CHECK (auth.uid() = id AND role = (SELECT role FROM public.profiles WHERE id = auth.uid()));

-- Complaints Policies
CREATE POLICY "Citizens can read their own complaints, Admins can read all"
ON public.complaints FOR SELECT
USING (auth.uid() = user_id OR public.is_admin());

CREATE POLICY "Citizens can create complaints for themselves with status Submitted"
ON public.complaints FOR INSERT
WITH CHECK (auth.uid() = user_id AND status = 'Submitted');

CREATE POLICY "Admins can update all complaint fields; Citizens can only dispute/reopen their resolved complaints"
ON public.complaints FOR UPDATE
USING (
    public.is_admin() OR
    (auth.uid() = user_id AND status IN ('Resolved', 'Closed'))
)
WITH CHECK (
    public.is_admin() OR
    (auth.uid() = user_id AND status = 'Reopened')
);

-- Attachments Policies
CREATE POLICY "Users can read attachments for complaints they can access"
ON public.complaint_attachments FOR SELECT
USING (
    EXISTS (
        SELECT 1 FROM public.complaints c
        WHERE c.id = complaint_id AND (c.user_id = auth.uid() OR public.is_admin())
    )
);

CREATE POLICY "Citizens can upload before photos, Admins can upload any"
ON public.complaint_attachments FOR INSERT
WITH CHECK (
    auth.uid() = uploaded_by AND (
        (attachment_type = 'before' AND EXISTS (SELECT 1 FROM public.complaints c WHERE c.id = complaint_id AND c.user_id = auth.uid()))
        OR public.is_admin()
    )
);

-- Notifications Policies
CREATE POLICY "Users can only read and update their own notifications"
ON public.notifications FOR SELECT
USING (auth.uid() = recipient_user_id);

CREATE POLICY "Users can mark their own notifications as read"
ON public.notifications FOR UPDATE
USING (auth.uid() = recipient_user_id)
WITH CHECK (auth.uid() = recipient_user_id);

-- Storage bucket configuration for complaint attachments
INSERT INTO storage.buckets (id, name, public)
VALUES ('complaint-attachments', 'complaint-attachments', false)
ON CONFLICT (id) DO NOTHING;

CREATE POLICY "Authenticated users can read complaint attachments"
ON storage.objects FOR SELECT
USING (bucket_id = 'complaint-attachments' AND auth.uid() IS NOT NULL);

CREATE POLICY "Authenticated users can upload complaint attachments"
ON storage.objects FOR INSERT
WITH CHECK (bucket_id = 'complaint-attachments' AND auth.uid() IS NOT NULL);
