import { UserRole } from '@/types/user.types';

/** Where to send a user immediately after a successful login, based on role. */
export function getPostLoginRedirect(role: UserRole): string {
  return role === UserRole.STAFF || role === UserRole.ADMIN ? '/admin' : '/student/course';
}
