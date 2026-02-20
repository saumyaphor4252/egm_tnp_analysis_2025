import etc.inputs.tnpSampleDef as tnpSamples
from libPython.tnpClassUtils import mkdir
import libPython.puReweighter as pu

puType = 0

for sName in tnpSamples.Prompt2022.keys():    
    sample = tnpSamples.Prompt2022[sName]
    if sample is None : continue
#    if not 'rec' in sName : continue
#    if not 'Winter17' in sName : continue
    if not 'DY' in sName: continue
    if not sample.isMC: continue
    
    trees = {}
    trees['ele'] = 'tnpEleIDs'
    trees['pho'] = 'tnpPhoIDs'
#    trees['rec'] = 'GsfElectronToSC'
    for tree in trees:
        dirout =  '/eos/cms/store/group/phys_egamma/ssaumya/2025TriggerSFs/'
        mkdir(dirout)
        
        if   puType == 0 : sample.set_puTree( dirout + '%s_%s.pu.puTree.root'   % (sample.name,tree) )
        elif puType == 1 : sample.set_puTree( dirout + '%s_%s.nVtx.puTree.root' % (sample.name,tree) )
        elif puType == 2 : sample.set_puTree( dirout + '%s_%s.rho.puTree.root'  % (sample.name,tree) )
        sample.set_tnpTree(trees[tree]+'/fitter_tree')
        sample.dump()
        pu.reweight(sample, puType )
    
