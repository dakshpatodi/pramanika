/**
 * Types mirroring the admin API (backend/app/schemas/admin.py and
 * admin_dashboard.py). Keep in sync by hand, like the other type files.
 * Money arrives as JSON numbers with two decimals.
 */

/** GET /api/admin/me - who the SERVER says the caller is (read from the database, not the token). */
export interface AdminMe {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  role: string;
}

export interface AdminRecentOrder {
  id: string;
  order_number: string | null;
  customer_name: string;
  customer_email: string;
  total_amount: number;
  /** Plain strings from the API; the UI narrows them before using the status badge. */
  status: string;
  payment_status: string;
  created_at: string;
}

export interface AdminDashboard {
  generated_at: string;
  orders: { total: number; by_status: Record<string, number> };
  customers: { total: number; new_last_30_days: number };
  products: { total: number; active: number; inactive: number; low_stock: number; out_of_stock: number };
  revenue: {
    currency: string;
    all_time: number;
    all_time_orders: number;
    last_30_days: number;
    last_30_days_orders: number;
  };
  recent_orders: AdminRecentOrder[];
}
