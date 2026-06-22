export enum UserRole {
  STUDENT = 'student',
  STAFF = 'staff',
  ADMIN = 'admin',
}

export interface User {
  id: number;
  email: string;
  role: UserRole;
  created_at: string;
  is_active: boolean;
}
