import jenkins.model.Jenkins

def jenkins = Jenkins.get()
jenkins.setNumExecutors(1)
jenkins.setLabelString("built-in docker linux")
jenkins.save()
