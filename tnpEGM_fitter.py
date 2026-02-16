
### python specific import
"""
Testing on small data for debugging:
------------------------------------
1. Test single sample: --sample data (or mcNom, etc.)
2. Test single bin: --iBin 0 (processes only first bin)
3. Limit bins: --maxBins 5 (processes first 5 bins)
4. Disable parallel: --noParallel (runs sequentially, easier to debug)

Example for quick testing:
  python3 tnpEGM_fitter.py etc/config/settings_ele_PromptReco2022FG.py \\
    --flag passingCutBasedTight94XV2 --createHists \\
    --sample data --noParallel --maxBins 3
"""
import argparse
import os
import sys
import pickle
import shutil
from multiprocessing import Pool


parser = argparse.ArgumentParser(description='tnp EGM fitter')
parser.add_argument('--checkBins'  , action='store_true'  , help = 'check  bining definition')
parser.add_argument('--createBins' , action='store_true'  , help = 'create bining definition')
parser.add_argument('--createHists', action='store_true'  , help = 'create histograms')
parser.add_argument('--sample'     , default='all'        , help = 'create histograms (per sample, expert only). Use sample name like "data" or "mcNom" to test single sample')
parser.add_argument('--altSig'     , action='store_true'  , help = 'alternate signal model fit')
parser.add_argument('--addGaus'    , action='store_true'  , help = 'add gaussian to alternate signal model failing probe')
parser.add_argument('--altBkg'     , action='store_true'  , help = 'alternate background model fit')
parser.add_argument('--doFit'      , action='store_true'  , help = 'fit sample (sample should be defined in settings.py)')
parser.add_argument('--mcSig'      , action='store_true'  , help = 'fit MC nom [to init fit parama]')
parser.add_argument('--doPlot'     , action='store_true'  , help = 'plotting')
parser.add_argument('--sumUp'      , action='store_true'  , help = 'sum up efficiencies')
parser.add_argument('--iBin'       , dest = 'binNumber'   , type = int,  default=-1, help='bin number (to refit individual bin). Use --iBin 0 to test first bin only')
parser.add_argument('--maxBins'    , type = int,  default=-1, help='limit number of bins to process (for testing). Use --maxBins 5 to test first 5 bins')
parser.add_argument('--noParallel' , action='store_true'  , help = 'disable parallel processing (run sequentially for easier debugging)')
parser.add_argument('--flag'       , default = None       , help ='WP to test')
parser.add_argument('settings'     , default = None       , help = 'setting file [mandatory]')


args = parser.parse_args()

print('===> settings %s <===' % args.settings)
importSetting = 'import %s as tnpConf' % args.settings.replace('/','.').split('.py')[0]
print(importSetting)
exec(importSetting)

### tnp library
import libPython.binUtils  as tnpBiner
import libPython.rootUtils as tnpRoot


if args.flag is None:
    print('[tnpEGM_fitter] flag is MANDATORY, this is the working point as defined in the settings.py')
    sys.exit(0)
    
if not args.flag in tnpConf.flags.keys() :
    print('[tnpEGM_fitter] flag %s not found in flags definitions' % args.flag)
    print('  --> define in settings first')
    print('  In settings I found flags: ')
    print(tnpConf.flags.keys())
    sys.exit(1)

outputDirectory = '%s/%s/' % (tnpConf.baseOutDir,args.flag)

print('===>  Output directory: ')
print(outputDirectory)


####################################################################
##### Create (check) Bins
####################################################################
if args.checkBins:
    tnpBins = tnpBiner.createBins(tnpConf.biningDef,tnpConf.cutBase)
    tnpBiner.tuneCuts( tnpBins, tnpConf.additionalCuts )
    for ib in range(len(tnpBins['bins'])):
        print(tnpBins['bins'][ib]['name'])
        print('  - cut: ',tnpBins['bins'][ib]['cut'])
    sys.exit(0)
    
if args.createBins:
    if os.path.exists( outputDirectory ):
            shutil.rmtree( outputDirectory )
    os.makedirs( outputDirectory )
    tnpBins = tnpBiner.createBins(tnpConf.biningDef,tnpConf.cutBase)
    tnpBiner.tuneCuts( tnpBins, tnpConf.additionalCuts )
    pickle.dump( tnpBins, open( '%s/bining.pkl'%(outputDirectory),'wb') )
    print('created dir: %s ' % outputDirectory)
    print('bining created successfully... ')
    print('Note than any additional call to createBins will overwrite directory %s' % outputDirectory)
    sys.exit(0)

tnpBins = pickle.load( open( '%s/bining.pkl'%(outputDirectory),'rb') )


####################################################################
##### Create Histograms
####################################################################
for s in tnpConf.samplesDef.keys():
    sample =  tnpConf.samplesDef[s]
    if sample is None: continue
    setattr( sample, 'tree'     ,'%s/fitter_tree' % tnpConf.tnpTreeDir )
    setattr( sample, 'histFile' , '%s/%s_%s.root' % ( outputDirectory , sample.name, args.flag ) )


if args.createHists:

    print(" ======== Creating Histograms ========")
    import libPython.histUtils as tnpHist
    import copy

    def tnpBins_converter(obj, parent_key=None):
        """
        A highly specific converter based on the exact needs of histUtils.pyx.
        - Keeps all keys as strings.
        - Converts values of 'name' and 'title' keys to bytes.
        - Keeps values of 'cut' keys as strings (they're used in string operations).
        - Converts all other strings to bytes (for Cython compatibility).
        - Recursively applies this logic.
        """
        if isinstance(obj, dict):
            new_dict = {}
            for k, v in obj.items():
                if k == 'cut' and isinstance(v, str):
                    # Keep 'cut' as string - it's used in string formatting operations
                    new_dict[k] = v
                elif k in ['name', 'title'] and isinstance(v, str):
                    # Convert 'name' and 'title' to bytes - used in C++ constructors
                    new_dict[k] = v.encode('utf-8')
                else:
                    # Recursively convert everything else
                    new_dict[k] = tnpBins_converter(v, parent_key=k)
            return new_dict
        elif isinstance(obj, list):
            return [tnpBins_converter(elem, parent_key=parent_key) for elem in obj]
        elif isinstance(obj, str):
            # Convert all other strings to bytes
            return obj.encode('utf-8')
        return obj

    tnpBins_to_pass = copy.deepcopy(tnpBins)
    tnpBins_to_pass = tnpBins_converter(tnpBins_to_pass)

    def parallel_hists(sampleType):
        sample =  tnpConf.samplesDef[sampleType]
        if sample is None : return
        if sampleType == args.sample or args.sample == 'all' :
            print('creating histogram for sample ')
            sample.dump()
            var = { 'name' : b'pair_mass', 'nbins' : 80, 'min' : 50, 'max': 130 }
            if sample.mcTruth:
                var = { 'name' : b'pair_mass', 'nbins' : 80, 'min' : 50, 'max': 130 }
            
            # Python 3 fix: sample.tree must be bytes for TChain constructor
            if hasattr(sample, 'tree') and isinstance(getattr(sample, 'tree'), str):
                setattr(sample, 'tree', getattr(sample, 'tree').encode('utf-8'))
            
            # Pass flag as string - histUtils.pyx will encode it internally with str.encode(flag)
            # Pass tnpBins_to_pass (converted) instead of tnpBins (original)
            flag = tnpConf.flags[args.flag]
            tnpHist.makePassFailHistograms( sample, flag, tnpBins_to_pass, var )
    
    pool = Pool()
    #pool.map(parallel_hists, tnpConf.samplesDef.keys())
    for k in tnpConf.samplesDef.keys(): parallel_hists(k)

    sys.exit(0)


####################################################################
##### Actual Fitter
####################################################################
sampleToFit = tnpConf.samplesDef['data']
if sampleToFit is None:
    print('[tnpEGM_fitter, prelim checks]: sample (data or MC) not available... check your settings')
    sys.exit(1)

sampleMC = tnpConf.samplesDef['mcNom']

if sampleMC is None:
    print('[tnpEGM_fitter, prelim checks]: MC sample not available... check your settings')
    sys.exit(1)
for s in tnpConf.samplesDef.keys():
    sample =  tnpConf.samplesDef[s]
    if sample is None: continue
    setattr( sample, 'mcRef'     , sampleMC )
    setattr( sample, 'nominalFit', '%s/%s_%s.nominalFit.root' % ( outputDirectory , sample.name, args.flag ) )
    setattr( sample, 'altSigFit' , '%s/%s_%s.altSigFit.root'  % ( outputDirectory , sample.name, args.flag ) )
    setattr( sample, 'altBkgFit' , '%s/%s_%s.altBkgFit.root'  % ( outputDirectory , sample.name, args.flag ) )



### change the sample to fit is mc fit
if args.mcSig :
    sampleToFit = tnpConf.samplesDef['mcNom']

if  args.doFit:
    print(" ======== Fitting ========")
    sampleToFit.dump()
    def parallel_fit(ib):
        if (args.binNumber >= 0 and ib == args.binNumber) or args.binNumber < 0:
            if args.altSig and not args.addGaus:
                tnpRoot.histFitterAltSig(  sampleToFit, tnpBins['bins'][ib], tnpConf.tnpParAltSigFit )
            elif args.altSig and args.addGaus:
                tnpRoot.histFitterAltSig(  sampleToFit, tnpBins['bins'][ib], tnpConf.tnpParAltSigFit_addGaus, 1)
            elif args.altBkg:
                tnpRoot.histFitterAltBkg(  sampleToFit, tnpBins['bins'][ib], tnpConf.tnpParAltBkgFit )
            else:
                tnpRoot.histFitterNominal( sampleToFit, tnpBins['bins'][ib], tnpConf.tnpParNomFit )
    
    # Determine which bins to process
    bins_to_process = range(len(tnpBins['bins']))
    if args.maxBins > 0:
        bins_to_process = range(min(args.maxBins, len(tnpBins['bins'])))
        print(f"Limiting to first {len(bins_to_process)} bins for testing")
    
    if args.noParallel:
        print("Running sequentially (no parallel processing)")
        for ib in bins_to_process:
            parallel_fit(ib)
    else:
        pool = Pool()
        pool.map(parallel_fit, bins_to_process)

    args.doPlot = True
     
####################################################################
##### dumping plots
####################################################################
if  args.doPlot:
    fileName = sampleToFit.nominalFit
    fitType  = 'nominalFit'
    if args.altSig : 
        fileName = sampleToFit.altSigFit
        fitType  = 'altSigFit'
    if args.altBkg : 
        fileName = sampleToFit.altBkgFit
        fitType  = 'altBkgFit'
        
    os.system('hadd -f %s %s' % (fileName, fileName.replace('.root', '-*.root')))

    plottingDir = '%s/plots/%s/%s' % (outputDirectory,sampleToFit.name,fitType)
    if not os.path.exists( plottingDir ):
        os.makedirs( plottingDir )
    shutil.copy('etc/inputs/index.php.listPlots','%s/index.php' % plottingDir)

    for ib in range(len(tnpBins['bins'])):
        if (args.binNumber >= 0 and ib == args.binNumber) or args.binNumber < 0:
            tnpRoot.histPlotter( fileName, tnpBins['bins'][ib], plottingDir )

    print(' ===> Plots saved in <=======')
#    print 'localhost/%s/' % plottingDir


####################################################################
##### dumping egamma txt file 
####################################################################
if args.sumUp:
    sampleToFit.dump()
    info = {
        'data'        : sampleToFit.histFile,
        'dataNominal' : sampleToFit.nominalFit,
        'dataAltSig'  : sampleToFit.altSigFit ,
        'dataAltBkg'  : sampleToFit.altBkgFit ,
        'mcNominal'   : sampleToFit.mcRef.histFile,
        'mcAlt'       : None,
        'tagSel'      : None
        }

    #if not tnpConf.samplesDef['mcAlt' ] is None:
    #    info['mcAlt'    ] = tnpConf.samplesDef['mcAlt' ].histFile
    if not tnpConf.samplesDef['tagSel'] is None:
        info['tagSel'   ] = tnpConf.samplesDef['tagSel'].histFile

    effis = None
    effFileName ='%s/egammaEffi.txt' % outputDirectory 
    fOut = open( effFileName,'w')
    
    for ib in range(len(tnpBins['bins'])):
        effis = tnpRoot.getAllEffi( info, tnpBins['bins'][ib] )

        ### formatting assuming 2D bining -- to be fixed        
        v1Range = tnpBins['bins'][ib]['title'].split(';')[1].split('<')
        v2Range = tnpBins['bins'][ib]['title'].split(';')[2].split('<')
        if ib == 0 :
            astr = '### var1 : %s' % v1Range[1]
            print(astr)
            fOut.write( astr + '\n' )
            astr = '### var2 : %s' % v2Range[1]
            print(astr)
            fOut.write( astr + '\n' )
            
        astr =  '%+8.5f\t%+8.5f\t%+8.5f\t%+8.5f\t%5.5f\t%5.5f\t%5.5f\t%5.5f\t%5.5f\t%5.5f\t%5.5f\t%5.5f' % (
            float(v1Range[0]), float(v1Range[2]),
            float(v2Range[0]), float(v2Range[2]),
            effis['dataNominal'][0],effis['dataNominal'][1],
            effis['mcNominal'  ][0],effis['mcNominal'  ][1],
            effis['dataAltBkg' ][0],
            effis['dataAltSig' ][0],
            effis['mcAlt' ][0],
            effis['tagSel'][0],
            )
        print(astr)
        fOut.write( astr + '\n' )
    fOut.close()

    print('Effis saved in file : ',  effFileName)
    import libPython.EGammaID_scaleFactors as egm_sf
    egm_sf.doEGM_SFs(effFileName,sampleToFit.lumi)
