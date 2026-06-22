import { AbilityBuilder, MongoAbility, createMongoAbility, subject } from "@casl/ability";
import type { User } from "@/types/user.types";
import { UserRole } from "@/types/user.types";

export type ERAction = "read" | "create" | "delete";

export type ERQuestionPermissionSubject = {
  created_by: number;
};

type ERSubject = "ERQuestion" | ERQuestionPermissionSubject;
type ERAbilityTuple = [ERAction, ERSubject];

export type ERAbility = MongoAbility<ERAbilityTuple>;

export function defineERAbility(user: User | null): ERAbility {
  const { can, build } = new AbilityBuilder<ERAbility>(createMongoAbility);

  if (user) {
    can("read", "ERQuestion");
    can("create", "ERQuestion");

    if (user.role === UserRole.STAFF) {
      can("delete", "ERQuestion");
    } else {
      can("delete", "ERQuestion", { created_by: user.id });
    }
  }

  return build({
    detectSubjectType: (item) => (typeof item === "string" ? item : "ERQuestion"),
  });
}

export function toERQuestionSubject(question: ERQuestionPermissionSubject) {
  return subject("ERQuestion", question);
}
