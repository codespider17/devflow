import com.cloudbees.plugins.credentials.CredentialsScope
import com.cloudbees.plugins.credentials.SystemCredentialsProvider
import com.cloudbees.plugins.credentials.domains.Domain
import hudson.util.Secret
import org.jenkinsci.plugins.plaincredentials.impl.StringCredentialsImpl

def callbackToken = System.getenv('DEVFLOW_PIPELINE_CALLBACK_TOKEN')
if (!callbackToken?.trim()) {
    throw new IllegalStateException('DEVFLOW_PIPELINE_CALLBACK_TOKEN is required')
}

def credentialId = 'devflow-pipeline-callback-token'
def replacement = new StringCredentialsImpl(
    CredentialsScope.GLOBAL,
    credentialId,
    'DevFlow Pipeline status callback token',
    Secret.fromString(callbackToken)
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

println('PASS: DevFlow callback credential ensured')
