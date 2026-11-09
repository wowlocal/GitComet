// Run only through cua_repl on the already-bound app. No AX or screenshots
// occur until all three numeric phases have ended. These are wheel requests,
// not a claim about native packet delivery, momentum, or presented frame rate.
var runEnergyWorkload = async (app, label) => {
  var result = {schema:'cua-scroll-timing-v1',plan_revision:2,label,events:[],commands:[],
    burst:{subcommands_per_group:10,pages_per_subcommand:0.1,scheduled_interval_ms:50,
      completed:0,start_gap_min_ms:null,start_gap_max_ms:null,
      maximum_lateness_ms:0,maximum_call_duration_ms:0},
    started_unix_ms:Date.now()};
  var base=result.started_unix_ms;
  var until=async(at)=>{var delay=at-Date.now();if(delay>0)await new Promise(r=>setTimeout(r,delay));};
  var mark=(name,state)=>result.events.push({name,state,unix_ms:Date.now()});
  mark('idle-before','begin');await until(base+10000);
  mark('idle-before','end');mark('scrolling','begin');
  for(var i=0;i<16;i++){
    var direction=['down','down','up','up'][i%4], scheduled=base+12000+i*1000;
    await until(scheduled);
    var command={index:i,direction,requested_pages:1,scheduled_unix_ms:scheduled,
      begin_unix_ms:Date.now(),subcommands_completed:0,
      subcall_count:10,subcall_pages:0.1,planned_spacing_ms:50,subcalls:[]};
    var previous=null;
    for(var j=0;j<10;j++){
      var due=scheduled+j*50;await until(due);var before=Date.now();
      await app.scroll([1200,800],direction,0.1);var after=Date.now();
      command.subcalls.push({index:j,scheduled_unix_ms:due,
        begin_unix_ms:before,end_unix_ms:after,requested_pages:0.1});
      if(previous!==null){var gap=before-previous;
        result.burst.start_gap_min_ms=Math.min(result.burst.start_gap_min_ms??gap,gap);
        result.burst.start_gap_max_ms=Math.max(result.burst.start_gap_max_ms??gap,gap);}
      previous=before;result.burst.completed++;command.subcommands_completed++;
      result.burst.maximum_lateness_ms=Math.max(result.burst.maximum_lateness_ms,before-due);
      result.burst.maximum_call_duration_ms=Math.max(result.burst.maximum_call_duration_ms,after-before);
    }
    command.end_unix_ms=Date.now();result.commands.push(command);
  }
  await until(base+30000);mark('scrolling','end');mark('idle-after','begin');
  await until(base+45000);mark('idle-after','end');result.ended_unix_ms=Date.now();
  return result;
};
