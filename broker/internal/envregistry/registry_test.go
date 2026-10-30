package envregistry

import (
	"strings"
	"testing"
)

const valid = `environments:
  - name: test-a
    kube_context: local-test
    namespace: test-a
    ssh_target: service/test-ssh
    credential_ref: env:TEST_A_SECRET
    acl_group: operators
`

func TestLoadAndLookup(t *testing.T) {
	r, err := Load(strings.NewReader(valid))
	if err != nil {
		t.Fatal(err)
	}
	env, err := r.Lookup("test-a")
	if err != nil || env.ACLGroup != "operators" {
		t.Fatal(env, err)
	}
	if _, err := r.Lookup("test-b"); err == nil {
		t.Fatal("unknown environment accepted")
	}
	names := r.Names()
	names[0] = "mutated"
	if r.Names()[0] != "test-a" {
		t.Fatal("registry mutated by caller")
	}
}

func TestRejectInvalidRegistry(t *testing.T) {
	cases := map[string]string{
		"empty":              "environments: []",
		"unknown":            valid + "    env: test-b\n",
		"missing":            strings.Replace(valid, "    credential_ref: env:TEST_A_SECRET\n", "", 1),
		"inline-secret":      strings.Replace(valid, "env:TEST_A_SECRET", "synthetic-password", 1),
		"target-option":      strings.Replace(valid, "service/test-ssh", "--context=test-b", 1),
		"target-shell":       strings.Replace(valid, "service/test-ssh", "pod/test;id", 1),
		"namespace-option":   strings.Replace(valid, "namespace: test-a", "namespace: --all", 1),
		"traversal":          strings.Replace(valid, "env:TEST_A_SECRET", "file:../outside", 1),
		"absolute-path":      strings.Replace(valid, "env:TEST_A_SECRET", "file:/tmp/secret", 1),
		"duplicate":          valid + strings.TrimPrefix(valid, "environments:\n"),
		"multiple-documents": valid + "---\n" + valid,
	}
	for name, input := range cases {
		t.Run(name, func(t *testing.T) {
			if _, err := Load(strings.NewReader(input)); err == nil {
				t.Fatal("invalid registry accepted")
			}
		})
	}
}

func TestFileReference(t *testing.T) {
	if _, err := Load(strings.NewReader(strings.Replace(valid, "env:TEST_A_SECRET", "file:test-a/ssh", 1))); err != nil {
		t.Fatal(err)
	}
}
