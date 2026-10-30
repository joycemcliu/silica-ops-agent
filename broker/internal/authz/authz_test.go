package authz

import (
	"strings"
	"testing"
	"time"

	"ops-agent/broker/internal/envregistry"
	"ops-agent/broker/internal/session"
)

const registryYAML = `environments:
  - name: test-a
    kube_context: local-a
    namespace: test-a
    ssh_target: service/test-a
    credential_ref: env:TEST_A_SECRET
    acl_group: group-a
  - name: test-b
    kube_context: local-b
    namespace: test-b
    ssh_target: service/test-b
    credential_ref: env:TEST_B_SECRET
    acl_group: group-b
`

const policyYAML = `users:
  alice:
    groups: [group-a]
    roles: [diagnose, knowledge]
  bob:
    groups: [group-b]
    roles: [diagnose]
groups:
  group-a:
    environments: [test-a]
    tools: [whoami, get_logs]
  group-b:
    environments: [test-b]
    tools: [whoami, get_logs, run_readonly]
`

func TestDefaultDenyAndEnvironmentBoundary(t *testing.T) {
	r, err := envregistry.Load(strings.NewReader(registryYAML))
	if err != nil {
		t.Fatal(err)
	}
	p, err := Load(strings.NewReader(policyYAML), r)
	if err != nil {
		t.Fatal(err)
	}
	now := time.Now()
	for _, tc := range []struct {
		user, env, role, tool string
		allowed               bool
	}{
		{"alice", "test-a", "diagnose", "get_logs", true},
		{"alice", "test-b", "diagnose", "get_logs", false},
		{"bob", "test-a", "diagnose", "run_readonly", false},
		{"alice", "test-a", "knowledge", "get_logs", false},
		{"bob", "test-b", "knowledge", "whoami", false},
		{"unknown", "test-a", "diagnose", "whoami", false},
		{"alice", "missing", "diagnose", "whoami", false},
		{"alice", "test-a", "diagnose", "run_readonly", false},
		{"alice", "test-a", "diagnose", "execute", false},
		{"bob", "test-b", "diagnose", "run_readonly", true},
	} {
		t.Run(tc.user+"/"+tc.env+"/"+tc.role+"/"+tc.tool, func(t *testing.T) {
			c, err := session.New(tc.user, tc.env, tc.role, time.Minute, now)
			if err != nil {
				t.Fatal(err)
			}
			env, err := p.Authorize(c, tc.tool, now)
			if (err == nil) != tc.allowed {
				t.Fatal("wrong authorization decision", err)
			}
			if tc.allowed && env.Name != c.Env {
				t.Fatal("cross-environment authorization")
			}
			if !tc.allowed && env.Name != "" {
				t.Fatal("denial leaked environment")
			}
			if _, err := p.Authorize(c, tc.tool, now.Add(time.Minute)); err == nil {
				t.Fatal("expired token authorized")
			}
		})
	}
}

func TestInvalidPolicy(t *testing.T) {
	r, _ := envregistry.Load(strings.NewReader(registryYAML))
	for _, input := range []string{
		"users: {}\ngroups: {}",
		policyYAML + "unknown: true",
		strings.Replace(policyYAML, "roles: [diagnose]", "roles: [solver]", 1),
		strings.Replace(policyYAML, "groups: [group-a]", "groups: [missing]", 1),
		strings.Replace(policyYAML, "environments: [test-a]", "environments: [test-b]", 1),
		strings.Replace(policyYAML, "whoami, get_logs", "write, get_logs", 1),
	} {
		if _, err := Load(strings.NewReader(input), r); err == nil {
			t.Fatal("invalid policy accepted")
		}
	}
}
