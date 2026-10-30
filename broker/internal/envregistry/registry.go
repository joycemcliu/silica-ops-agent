// Package envregistry loads the broker's trusted environment references.
package envregistry

import (
	"errors"
	"io"
	"regexp"
	"sort"
	"strings"

	"ops-agent/broker/internal/config"
)

type Environment struct {
	Name          string `yaml:"name" json:"name"`
	KubeContext   string `yaml:"kube_context" json:"-"`
	Namespace     string `yaml:"namespace" json:"-"`
	SSHTarget     string `yaml:"ssh_target" json:"-"`
	CredentialRef string `yaml:"credential_ref" json:"-"`
	ACLGroup      string `yaml:"acl_group" json:"-"`
}

type Registry struct{ environments map[string]Environment }

var (
	identifier  = regexp.MustCompile(`^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$`)
	contextName = regexp.MustCompile(`^[a-zA-Z0-9][a-zA-Z0-9_./:@-]{0,252}$`)
	namespace   = regexp.MustCompile(`^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$`)
	target      = regexp.MustCompile(`^(?:(?:pod|pods|service|services)/)?[a-zA-Z0-9][a-zA-Z0-9.-]{0,252}$`)
	envRef      = regexp.MustCompile(`^env:[A-Z_][A-Z0-9_]*$`)
	fileRef     = regexp.MustCompile(`^file:[a-zA-Z0-9][a-zA-Z0-9_./-]*$`)
)

func Load(r io.Reader) (*Registry, error) {
	var doc struct {
		Environments []Environment `yaml:"environments"`
	}
	if err := config.Decode(r, &doc); err != nil {
		return nil, err
	}
	if len(doc.Environments) == 0 {
		return nil, errors.New("at least one environment is required")
	}
	registry := &Registry{environments: make(map[string]Environment)}
	for _, env := range doc.Environments {
		if !identifier.MatchString(env.Name) || !contextName.MatchString(env.KubeContext) ||
			!namespace.MatchString(env.Namespace) || !target.MatchString(env.SSHTarget) ||
			!identifier.MatchString(env.ACLGroup) || !validRef(env.CredentialRef) {
			return nil, errors.New("environment has missing or invalid fields")
		}
		if _, exists := registry.environments[env.Name]; exists {
			return nil, errors.New("duplicate environment name")
		}
		registry.environments[env.Name] = env
	}
	return registry, nil
}

func validRef(ref string) bool {
	if envRef.MatchString(ref) {
		return true
	}
	if !fileRef.MatchString(ref) {
		return false
	}
	// References are relative to the secret store's root, never the repository.
	for _, part := range strings.Split(strings.TrimPrefix(ref, "file:"), "/") {
		if part == "" || part == "." || part == ".." {
			return false
		}
	}
	return true
}

func (r *Registry) Lookup(name string) (Environment, error) {
	env, ok := r.environments[name]
	if !ok {
		return Environment{}, errors.New("unknown environment")
	}
	return env, nil
}

func (r *Registry) Names() []string {
	names := make([]string, 0, len(r.environments))
	for name := range r.environments {
		names = append(names, name)
	}
	sort.Strings(names)
	return names
}
