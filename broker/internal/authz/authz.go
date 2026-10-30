// Package authz implements default-deny user, group, environment and tool policy.
package authz

import (
	"errors"
	"io"
	"slices"
	"time"

	"ops-agent/broker/internal/config"
	"ops-agent/broker/internal/envregistry"
	"ops-agent/broker/internal/session"
)

type User struct {
	Groups []string `yaml:"groups"`
	Roles  []string `yaml:"roles"`
}

type Group struct {
	Environments []string `yaml:"environments"`
	Tools        []string `yaml:"tools"`
}

type Policy struct {
	users    map[string]User
	groups   map[string]Group
	registry *envregistry.Registry
}

var toolsByRole = map[string][]string{
	session.Diagnose:  {"whoami", "list_hosts", "get_logs", "run_readonly"},
	session.Knowledge: {"whoami"},
}

func Load(reader io.Reader, registry *envregistry.Registry) (*Policy, error) {
	if registry == nil {
		return nil, errors.New("environment registry is required")
	}
	var doc struct {
		Users  map[string]User  `yaml:"users"`
		Groups map[string]Group `yaml:"groups"`
	}
	if err := config.Decode(reader, &doc); err != nil {
		return nil, err
	}
	if len(doc.Users) == 0 || len(doc.Groups) == 0 {
		return nil, errors.New("policy requires users and groups")
	}
	for name, group := range doc.Groups {
		if name == "" || len(group.Environments) == 0 || len(group.Tools) == 0 {
			return nil, errors.New("empty group grant")
		}
		for _, envName := range group.Environments {
			env, err := registry.Lookup(envName)
			if err != nil || env.ACLGroup != name {
				return nil, errors.New("group environment does not match registry ACL")
			}
		}
		for _, tool := range group.Tools {
			if !slices.Contains(toolsByRole[session.Diagnose], tool) {
				return nil, errors.New("policy grants an unknown or unsafe tool")
			}
		}
	}
	for name, user := range doc.Users {
		if name == "" || len(user.Groups) == 0 || len(user.Roles) == 0 {
			return nil, errors.New("empty user grant")
		}
		for _, group := range user.Groups {
			if _, ok := doc.Groups[group]; !ok {
				return nil, errors.New("user references unknown group")
			}
		}
		for _, role := range user.Roles {
			if _, ok := toolsByRole[role]; !ok {
				return nil, errors.New("unknown or unapproved role")
			}
		}
	}
	return &Policy{users: doc.Users, groups: doc.Groups, registry: registry}, nil
}

// Authorize has no environment argument: it resolves the signed claim's env.
// Only verified claims may be passed here; the transport must use a Verifier.
func (p *Policy) Authorize(claims session.Claims, tool string, now time.Time) (envregistry.Environment, error) {
	denied := errors.New("access denied")
	if err := claims.Validate(now); err != nil {
		return envregistry.Environment{}, denied
	}
	user, ok := p.users[claims.User]
	if !ok || !slices.Contains(user.Roles, claims.Role) || !slices.Contains(toolsByRole[claims.Role], tool) {
		return envregistry.Environment{}, denied
	}
	env, err := p.registry.Lookup(claims.Env)
	if err != nil || !slices.Contains(user.Groups, env.ACLGroup) {
		return envregistry.Environment{}, denied
	}
	group := p.groups[env.ACLGroup]
	if !slices.Contains(group.Environments, env.Name) || !slices.Contains(group.Tools, tool) {
		return envregistry.Environment{}, denied
	}
	return env, nil
}
