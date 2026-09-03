import com.cloudbees.plugins.credentials.CredentialsScope
import com.cloudbees.plugins.credentials.SystemCredentialsProvider
import com.cloudbees.plugins.credentials.domains.Domain
import com.cloudbees.plugins.credentials.impl.UsernamePasswordCredentialsImpl

def harborUsername = System.getenv('DEVFLOW_HARBOR_PUSH_USERNAME')
def harborSecret = System.getenv('DEVFLOW_HARBOR_PUSH_SECRET')

if (!harborUsername?.trim()) {
    throw new IllegalStateException('DEVFLOW_HARBOR_PUSH_USERNAME is required')
}
if (!harborSecret?.trim()) {
    throw new IllegalStateException('DEVFLOW_HARBOR_PUSH_SECRET is required')
}

def credentialId = 'devflow-harbor-push'
def replacement = new UsernamePasswordCredentialsImpl(
    CredentialsScope.GLOBAL,
    credentialId,
    'DevFlow Harbor project Robot with repository pull and push',
    harborUsername,
    harborSecret
)
def store = SystemCredentialsProvider.getInstance().getStore()
def domain = Domain.global()
def existing = store.getCredentials(domain).find {
    credential -> credential.id == credentialId
}

if (existing == null) {
    store.addCredentials(domain, replacement)
} else {
    store.updateCredentials(domain, existing, replacement)
}

println('PASS: DevFlow Harbor push credential ensured')
